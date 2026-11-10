"""Output-size baseline for accessory state persistence.

json.dump writes ', ' and ': ' by default. The length below is the UTF-8
size of that document. Compact separators are still JSON and load back to
the same state; this script only reports the current size.

Run from the repository root:

    python3 osspr-intake/harness/output_bytes.py persist
"""

from __future__ import annotations

import argparse
import io
import sys
from pathlib import Path
from uuid import UUID

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey  # noqa: E402

from pyhap.const import HAP_PERMISSIONS  # noqa: E402
from pyhap.encoder import AccessoryEncoder  # noqa: E402
from pyhap.state import State  # noqa: E402


def _state() -> State:
    state = State(address="127.0.0.1", mac="AA:BB:CC:DD:EE:FF", pincode=b"123-45-678")
    private = Ed25519PrivateKey.from_private_bytes(bytes(range(32)))
    state.private_key = private
    state.public_key = private.public_key()
    state.config_version = 3
    state.accessories_hash = "cafebabe"
    clients = (
        (
            "11111111-1111-1111-1111-111111111111",
            HAP_PERMISSIONS.ADMIN,
            bytes(range(32)),
        ),
        (
            "22222222-2222-2222-2222-222222222222",
            HAP_PERMISSIONS.USER,
            bytes(range(32, 64)),
        ),
        (
            "33333333-3333-3333-3333-333333333333",
            HAP_PERMISSIONS.USER,
            bytes([0xAB]) * 32,
        ),
        (
            "44444444-4444-4444-4444-444444444444",
            HAP_PERMISSIONS.ADMIN,
            bytes([0xCD]) * 32,
        ),
    )
    for text, perms, public in clients:
        state.add_paired_client(str(UUID(text)).upper().encode("ascii"), public, perms)
    return state


STATE = _state()


def persist_document() -> bytes:
    buffer = io.StringIO()
    AccessoryEncoder.persist(buffer, STATE)
    return buffer.getvalue().encode("utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workload", choices=("persist",))
    parser.add_argument("--runs", type=int, default=1)
    args = parser.parse_args()
    if args.workload != "persist":
        raise SystemExit(f"unknown workload {args.workload}")
    values = [len(persist_document()) for _ in range(args.runs)]
    if args.runs == 1:
        print(values[0])
        return
    for value in values:
        print(value)


if __name__ == "__main__":
    main()
