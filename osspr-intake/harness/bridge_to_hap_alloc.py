"""Allocation cost of Bridge.to_HAP on a warm large bridge.

Characteristic.to_HAP is already cached after the first serialization.
A second GET /accessories (another controller, or a refetch) still builds
a new dict and list for every service and accessory. This harness counts
those live allocations.
"""

from __future__ import annotations

import gc
import hashlib
import json
import sys
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HARNESS = Path(__file__).resolve().parent
for path in (str(ROOT), str(HARNESS)):
    if path not in sys.path:
        sys.path.insert(0, path)

from pyhap.loader import Loader  # noqa: E402
from pyhap.util import to_sorted_hap_json  # noqa: E402
from workload import ACCESSORY_COUNT, _LoaderDriver, build_bridge  # noqa: E402

RUNS = 5
# sha256 of the sorted HAP JSON of this workload on unmodified code.
EXPECTED_SHA256 = "bca38964f17d1dbcefc370985cad3b173d3890deb2981ed22147714229df939c"


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


def main() -> None:
    bridge = build_bridge(_LoaderDriver(Loader()), ACCESSORY_COUNT)
    # Warm characteristic to_HAP caches. The measured calls are refetches.
    reference = to_sorted_hap_json({"accessories": bridge.to_HAP()})
    digest = hashlib.sha256(reference).hexdigest()
    if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
        raise SystemExit(f"HAP payload changed: {digest}")

    samples: list[int] = []
    for _ in range(RUNS):
        count, hap = _allocations(bridge.to_HAP)
        if to_sorted_hap_json({"accessories": hap}) != reference:
            raise SystemExit("Bridge.to_HAP output changed between runs")
        samples.append(count)

    samples.sort()
    median = samples[len(samples) // 2]
    noise_pct = (samples[-1] - samples[0]) / median * 100 if median else 0.0
    print(
        json.dumps(
            {
                "metric_kind": "allocations",
                "function": "Bridge.to_HAP",
                "samples": samples,
                "median": median,
                "noise_pct": round(noise_pct, 4),
                "sha256": digest,
                "accessories": ACCESSORY_COUNT,
            }
        )
    )


if __name__ == "__main__":
    main()
