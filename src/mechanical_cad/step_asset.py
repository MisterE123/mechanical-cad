"""Bounded immutable STEP payloads; no filesystem or native geometry dependencies."""

import base64
import binascii
import hashlib
import re

MAX_STEP_BYTES = 512 * 1024


def encode_step(data):
    if type(data) is not bytes or not 0 < len(data) <= MAX_STEP_BYTES:
        raise ValueError("STEP import requires 1 to 524288 bytes (512 KiB).")
    # ISO-10303-21 clear-text exchange only, not archives, XML or mutable paths.
    stripped = data.strip()
    if not stripped.startswith(b"ISO-10303-21;") or not stripped.endswith(b"END-ISO-10303-21;"):
        raise ValueError("Import requires a complete ISO-10303-21 STEP exchange file.")
    return {
        "encoding": "base64",
        "sha256": hashlib.sha256(data).hexdigest(),
        "data": base64.b64encode(data).decode("ascii"),
    }


def decode_step(asset):
    if type(asset) is not dict or set(asset) != {"encoding", "sha256", "data"}:
        raise ValueError("STEP data requires exact encoding, sha256 and data fields.")
    if asset["encoding"] != "base64":
        raise ValueError("STEP data encoding must be base64.")
    checksum, encoded = asset["sha256"], asset["data"]
    if type(checksum) is not str or not re.fullmatch(r"[0-9a-f]{64}", checksum):
        raise ValueError("STEP checksum must be a lowercase SHA-256 digest.")
    if type(encoded) is not str or not 0 < len(encoded) <= 4 * ((MAX_STEP_BYTES + 2) // 3):
        raise ValueError("Embedded STEP exceeds the 512 KiB decoded limit.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as exc:
        raise ValueError("STEP data is not strict base64.") from exc
    expected = encode_step(data)
    if asset != expected:
        raise ValueError("STEP bytes do not match the checksum or canonical base64 encoding.")
    return data
