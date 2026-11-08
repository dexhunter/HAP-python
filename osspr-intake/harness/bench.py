"""Frozen baselines for unused HAP-python hot functions.

Run from the repository root, one target per command:

    taskset -c 0 python3 osspr-intake/harness/bench.py tlv-encode
    taskset -c 0 python3 osspr-intake/harness/bench.py hksv-iter
    taskset -c 0 python3 osspr-intake/harness/bench.py to-valid-value
    taskset -c 0 python3 osspr-intake/harness/bench.py is-allowed-sender
    taskset -c 0 python3 osspr-intake/harness/bench.py to-hap

Prints ``median_ms``, ``noise_pct`` (pstdev / median * 100), and the samples.
The timed callable and its inputs are fixed. Setup sits outside the timer.
"""

from __future__ import annotations

import logging
import os
import statistics
import sys
import time
from pathlib import Path
from typing import Callable

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

logging.disable(logging.CRITICAL)

try:
    os.sched_setaffinity(0, {0})
except (AttributeError, OSError):
    pass

WARMUP = 3
REPEATS = 11


def measure(fn: Callable[[], object]) -> None:
    """Time ``fn`` and print the median and relative spread."""
    for _ in range(WARMUP):
        fn()
    samples_ms: list[float] = []
    for _ in range(REPEATS):
        start = time.perf_counter()
        fn()
        samples_ms.append((time.perf_counter() - start) * 1000.0)
    median_ms = statistics.median(samples_ms)
    noise_pct = statistics.pstdev(samples_ms) / median_ms * 100.0
    rendered = ",".join(f"{sample:.4f}" for sample in samples_ms)
    print(f"median_ms={median_ms:.4f}")
    print(f"noise_pct={noise_pct:.4f}")
    print(f"samples_ms={rendered}")


def bench_tlv_encode() -> None:
    """Encode one 512 KiB TLV value (fragmented every 255 bytes)."""
    from pyhap import tlv

    payload = b"Z" * (512 * 1024)
    tag = b"\x01"

    def run() -> None:
        encoded = tlv.encode(tag, payload)
        if len(encoded) < len(payload):
            raise RuntimeError("encoded TLV shrank")

    measure(run)


def bench_hksv_iter() -> None:
    """Walk one 512 KiB TLV value split into 255-byte fragments."""
    from pyhap.hksv_recording import _iter

    payload = bytes(range(256)) * (2 * 1024)
    parts: list[bytes] = []
    tag = 3
    for offset in range(0, len(payload), 255):
        chunk = payload[offset : offset + 255]
        parts.append(bytes((tag, len(chunk))))
        parts.append(chunk)
    fragmented = b"".join(parts)

    def run() -> None:
        # Eight passes make one sample long enough to absorb a scheduling blip.
        total = 0
        for _ in range(8):
            for _tag, value in _iter(fragmented):
                total += len(value)
        if total != len(payload) * 8:
            raise RuntimeError("fragmented TLV value was truncated")

    measure(run)


def bench_to_valid_value() -> None:
    """Coerce a float through CurrentTemperature min/max/step 80_000 times."""
    from pyhap.loader import get_loader

    char = get_loader().get_char("CurrentTemperature")
    value = 21.37

    def run() -> None:
        coerced = 0.0
        for _ in range(80_000):
            coerced = char.to_valid_value(value)
        if coerced != 21.4:
            raise RuntimeError(f"unexpected coerced value {coerced}")

    measure(run)


def bench_is_allowed_sender() -> None:
    """Check the talkback controller address 160_000 times."""
    from pyhap.camera_talkback import is_allowed_sender

    source = ("192.168.1.20", 53572)
    controller = "192.168.1.20"

    def run() -> None:
        allowed = 0
        for _ in range(160_000):
            if is_allowed_sender(source, controller):
                allowed += 1
        if allowed != 160_000:
            raise RuntimeError("controller address was rejected")

    measure(run)


def bench_to_hap() -> None:
    """Rebuild one getter-backed characteristic HAP dict 30_000 times."""
    import tempfile

    from pyhap.accessory import Accessory
    from pyhap.accessory_driver import AccessoryDriver
    from pyhap.const import CATEGORY_SWITCH

    persist_dir = tempfile.mkdtemp(prefix="hap-intake-")
    driver = AccessoryDriver(
        address="127.0.0.1",
        listen_address="127.0.0.1",
        port=51826,
        persist_file=os.path.join(persist_dir, "accessory.state"),
        advertise=False,
    )

    class Switch(Accessory):
        category = CATEGORY_SWITCH

        def __init__(self) -> None:
            super().__init__(driver, "Intake Switch", aid=1)
            service = self.add_preload_service("Switch")
            self.char_on = service.get_characteristic("On")
            # A getter disables the HAP representation cache, which is how
            # Home Assistant accessories serve live values.
            self.char_on.getter_callback = lambda: self.char_on._value

    accessory = Switch()
    driver.accessory = accessory
    char = accessory.char_on

    def run() -> None:
        reps = None
        for _ in range(30_000):
            reps = char.to_HAP(True)
        if not reps or "value" not in reps:
            raise RuntimeError("HAP representation missing value")

    measure(run)


TARGETS = {
    "tlv-encode": bench_tlv_encode,
    "hksv-iter": bench_hksv_iter,
    "to-valid-value": bench_to_valid_value,
    "is-allowed-sender": bench_is_allowed_sender,
    "to-hap": bench_to_hap,
}


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in TARGETS:
        names = ", ".join(TARGETS)
        print(f"usage: python3 osspr-intake/harness/bench.py <{names}>", file=sys.stderr)
        raise SystemExit(2)
    TARGETS[sys.argv[1]]()


if __name__ == "__main__":
    main()
