"""Allocation baselines for TLV and HDS encode/decode.

Counts OBJ-domain malloc, calloc, and realloc calls inside one workload
invocation. Garbage collection is disabled for the window so cyclic-GC
bookkeeping does not add noise. Inputs are built before the window.

Run from the repository root:

    python3 osspr-intake/harness/allocs.py tlv-encode
    python3 osspr-intake/harness/allocs.py tlv-decode
    python3 osspr-intake/harness/allocs.py hds-encode
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pyhap import tlv  # noqa: E402
from pyhap.hds_protocol import decode as hds_decode  # noqa: E402
from pyhap.hds_protocol import encode as hds_encode  # noqa: E402

# 65536 % 255 == 1, so the fragment loop and the short remainder both run.
TLV_VALUE = bytes(i % 251 for i in range(65536))
TLV_ENCODED = tlv.encode(b"\x01", TLV_VALUE, b"\x02", b"ok")

_PACKETS = [
    {"data": bytes([i & 0xFF]) * 64, "sequence": i, "last": i == 31}
    for i in range(32)
]
HDS_VALUE = {
    "streamId": 7,
    "reason": None,
    "endOfStream": False,
    "progress": 1.5,
    "clock": 2**40,
    "delta": -2,
    "packets": _PACKETS,
    "meta": {f"k{i:02d}": i for i in range(16)},
}


def _load_counter():
    source = Path(__file__).with_name("alloccount.c")
    cached = Path("/tmp/osspr-hap-alloccount.so")
    if not cached.exists() or cached.stat().st_mtime < source.stat().st_mtime:
        include = sysconfig.get_path("include")
        subprocess.check_call(
            [
                "gcc",
                "-shared",
                "-fPIC",
                "-O2",
                f"-I{include}",
                str(source),
                "-o",
                str(cached),
            ]
        )
    spec = importlib.util.spec_from_file_location("alloccount", cached)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {cached}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.install()
    return module


_COUNTER = _load_counter()


def measure(fn) -> int:
    """Return OBJ-domain allocation events while calling fn once."""
    gc.collect()
    gc.disable()
    try:
        _COUNTER.start()
        try:
            fn()
        finally:
            _COUNTER.stop()
        return int(_COUNTER.count())
    finally:
        gc.enable()


def run_tlv_encode() -> None:
    tlv.encode(b"\x01", TLV_VALUE, b"\x02", b"ok")


def run_tlv_decode() -> None:
    tlv.decode(TLV_ENCODED)


def run_hds_encode() -> None:
    hds_encode(HDS_VALUE)


WORKLOADS = {
    "tlv-encode": run_tlv_encode,
    "tlv-decode": run_tlv_decode,
    "hds-encode": run_hds_encode,
}


def _check_results() -> None:
    encoded = tlv.encode(b"\x01", TLV_VALUE, b"\x02", b"ok")
    if encoded != TLV_ENCODED:
        raise SystemExit("tlv encode is not stable")
    decoded = tlv.decode(encoded)
    if decoded != {b"\x01": TLV_VALUE, b"\x02": b"ok"}:
        raise SystemExit("tlv round trip changed")
    payload = hds_encode(HDS_VALUE)
    if hds_decode(payload) != HDS_VALUE:
        raise SystemExit("hds round trip changed")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workload", choices=sorted(WORKLOADS))
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    _check_results()
    fn = WORKLOADS[args.workload]
    # Warm the function and the allocator hook before recording.
    for _ in range(3):
        measure(fn)
    values = [measure(fn) for _ in range(args.runs)]
    if args.runs == 1:
        print(values[0])
        return
    for value in values:
        print(value)


if __name__ == "__main__":
    main()
