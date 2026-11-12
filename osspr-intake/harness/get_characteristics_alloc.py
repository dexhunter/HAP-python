"""Allocation cost of one full characteristic read on a large bridge.

HomeKit controllers poll with GET /characteristics?id=... . One read of
every characteristic on the bridge allocates a fresh response dict per id.
"""

from __future__ import annotations

import asyncio
import gc
import hashlib
import json
import os
import sys
import tempfile
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent
for path in (str(ROOT), str(HARNESS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from pyhap.accessory_driver import AccessoryDriver  # noqa: E402
from pyhap.loader import Loader  # noqa: E402
from pyhap.util import to_sorted_hap_json  # noqa: E402
from workload import ACCESSORY_COUNT, build_bridge  # noqa: E402

RUNS = 5
EXPECTED_SHA256 = "3938d9ee85fa652fdcb04f758ee52dd1bcbe7c235dc861f25b8657f7608e4f67"


def _allocations(fn):  # type: ignore[no-untyped-def]
    gc.collect()
    gc.disable()
    try:
        tracemalloc.start()
        before = tracemalloc.take_snapshot()
        result = fn()
        after = tracemalloc.take_snapshot()
        count = 0
        for stat in after.compare_to(before, "traceback"):
            if stat.count_diff <= 0:
                continue
            filename = stat.traceback[0].filename
            if filename.endswith("tracemalloc.py"):
                continue
            count += stat.count_diff
        return count, result
    finally:
        tracemalloc.stop()
        gc.enable()


def _char_ids(bridge):  # type: ignore[no-untyped-def]
    ids: list[str] = []
    accessories = (bridge, *bridge.accessories.values())
    for accessory in accessories:
        for service in accessory.services:
            for char in service.characteristics:
                iid = accessory.iid_manager.get_iid(char)
                ids.append(f"{accessory.aid}.{iid}")
    return ids


def main() -> None:
    loop = asyncio.new_event_loop()
    descriptor, persist_path = tempfile.mkstemp(prefix="hap-intake-state-")
    os.close(descriptor)
    try:
        driver = AccessoryDriver(
            loop=loop,
            address="127.0.0.1",
            port=51827,
            persist_file=persist_path,
            advertise=False,
            loader=Loader(),
        )
        bridge = build_bridge(driver, ACCESSORY_COUNT)
        driver.accessory = bridge
        char_ids = _char_ids(bridge)
        reference = to_sorted_hap_json(driver.get_characteristics(char_ids))
        digest = hashlib.sha256(reference).hexdigest()
        if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
            raise SystemExit(f"characteristic read changed: {digest}")

        samples: list[int] = []
        for _ in range(RUNS):
            count, response = _allocations(
                lambda: driver.get_characteristics(char_ids)
            )
            if to_sorted_hap_json(response) != reference:
                raise SystemExit("get_characteristics output changed between runs")
            samples.append(count)
    finally:
        os.unlink(persist_path)

    samples.sort()
    median = samples[len(samples) // 2]
    noise_pct = (samples[-1] - samples[0]) / median * 100 if median else 0.0
    print(
        json.dumps(
            {
                "metric_kind": "allocations",
                "function": "AccessoryDriver.get_characteristics",
                "samples": samples,
                "median": median,
                "noise_pct": round(noise_pct, 4),
                "sha256": digest,
                "accessories": ACCESSORY_COUNT,
                "characteristics": len(char_ids),
            }
        )
    )


if __name__ == "__main__":
    main()
