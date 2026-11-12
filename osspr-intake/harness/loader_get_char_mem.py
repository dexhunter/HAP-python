"""Peak traced memory of building a large bridge.

Loader.get_char copies the catalog dict for every characteristic. On a
large bridge those copies dominate the retained object graph.
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

from pyhap.accessory import Accessory  # noqa: E402
from pyhap.loader import Loader  # noqa: E402
from pyhap.util import to_sorted_hap_json  # noqa: E402
from workload import (  # noqa: E402
    ACCESSORY_COUNT,
    DEVICE_PLANS,
    _LoaderDriver,
    build_bridge,
)

RUNS = 5
EXPECTED_SHA256 = "7684060f53461e87d5a6c84ac2df8e3cad393b70a92845495669e7eefbd84cce"


def _build_and_measure(loader: Loader) -> tuple[int, int, bytes]:
    gc.collect()
    gc.disable()
    try:
        tracemalloc.start()
        bridge = build_bridge(_LoaderDriver(loader), ACCESSORY_COUNT)
        _current, peak = tracemalloc.get_traced_memory()
        snapshot = tracemalloc.take_snapshot()
        copy_bytes = 0
        for stat in snapshot.statistics("lineno"):
            frame = stat.traceback[0]
            if frame.filename.endswith("loader.py") and frame.lineno == 47:
                copy_bytes += stat.size
        payload = to_sorted_hap_json(
            {"accessories": bridge.to_HAP(include_value=False)}
        )
        return peak, copy_bytes, payload
    finally:
        tracemalloc.stop()
        gc.enable()


def _warm(loader: Loader) -> None:
    """Fill the HAP-type caches so measured builds do not pay one-time fills."""
    driver = _LoaderDriver(loader)
    for _category, service_name, extra in DEVICE_PLANS:
        accessory = Accessory(driver, "warm", aid=2)
        accessory.add_preload_service(service_name, chars=extra)
    gc.collect()


def main() -> None:
    loader = Loader()
    _warm(loader)
    peaks: list[int] = []
    copy_bytes = 0
    digest = ""
    reference = b""
    for index in range(RUNS):
        peak, copies, payload = _build_and_measure(loader)
        if index == 0:
            reference = payload
            digest = hashlib.sha256(payload).hexdigest()
            copy_bytes = copies
            if EXPECTED_SHA256 and digest != EXPECTED_SHA256:
                raise SystemExit(f"bridge metadata changed: {digest}")
        elif payload != reference:
            raise SystemExit("bridge metadata changed between runs")
        peaks.append(peak)

    peaks.sort()
    median = peaks[len(peaks) // 2]
    noise_pct = (peaks[-1] - peaks[0]) / median * 100 if median else 0.0
    print(
        json.dumps(
            {
                "metric_kind": "peak_memory_bytes",
                "function": "Loader.get_char",
                "samples": peaks,
                "median": median,
                "noise_pct": round(noise_pct, 4),
                "catalog_copy_bytes": copy_bytes,
                "sha256": digest,
                "accessories": ACCESSORY_COUNT,
            }
        )
    )


if __name__ == "__main__":
    main()
