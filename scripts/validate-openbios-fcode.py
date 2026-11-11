#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate the IEEE-1275 header emitted by OpenBIOS toke."""

from __future__ import annotations

import hashlib
import pathlib
import sys

HEADER_SIZE = 8  # starter byte + 7-byte FCode header
IEEE1275_FORMAT = 0x08


def validate(path: pathlib.Path) -> str:
    try:
        data = path.read_bytes()
    except OSError as exc:
        raise ValueError(f"cannot read FCode image {path}: {exc}") from exc

    if len(data) < HEADER_SIZE:
        raise ValueError(
            f"FCode image is too small: {len(data)} bytes, expected at least {HEADER_SIZE}"
        )

    starter = data[0]
    format_byte = data[1]
    stored_checksum = int.from_bytes(data[2:4], "big")
    stored_length = int.from_bytes(data[4:8], "big")

    if format_byte != IEEE1275_FORMAT:
        raise ValueError(
            f"unexpected FCode format 0x{format_byte:02x}; expected 0x{IEEE1275_FORMAT:02x}"
        )

    if stored_length != len(data):
        raise ValueError(
            f"FCode length mismatch: header={stored_length} actual={len(data)}"
        )

    calculated_checksum = sum(data[HEADER_SIZE:]) & 0xFFFF
    if stored_checksum != calculated_checksum:
        raise ValueError(
            "FCode checksum mismatch: "
            f"header=0x{stored_checksum:04x} calculated=0x{calculated_checksum:04x}"
        )

    digest = hashlib.sha256(data).hexdigest()
    return (
        "OpenBIOS VGA FCode: "
        f"starter=0x{starter:02x} format=0x{format_byte:02x} "
        f"size={len(data)} checksum=0x{stored_checksum:04x} "
        f"sha256={digest} path={path}"
    )


def main(argv: list[str]) -> int:
    if len(argv) != 1:
        print("usage: validate-openbios-fcode.py QEMU,VGA.bin", file=sys.stderr)
        return 2

    path = pathlib.Path(argv[0])
    try:
        result = validate(path)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
