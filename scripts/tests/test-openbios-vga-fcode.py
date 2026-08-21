#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
VALIDATOR = ROOT / "scripts" / "validate-openbios-fcode.py"


def make_image(body: bytes = b"\x00") -> bytes:
    checksum = sum(body) & 0xFFFF
    length = 8 + len(body)
    return (
        b"\xf3\x08"
        + checksum.to_bytes(2, "big")
        + length.to_bytes(4, "big")
        + body
    )


def run_validator(path: pathlib.Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(VALIDATOR), str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)

        valid = root / "QEMU,VGA.bin"
        valid.write_bytes(make_image(b"\x00\x10\x20"))
        result = run_validator(valid)
        assert result.returncode == 0, result.stderr
        assert "format=0x08" in result.stdout
        assert "size=11" in result.stdout
        assert "checksum=0x0030" in result.stdout
        assert "sha256=" in result.stdout

        bad_length = root / "bad-length.bin"
        image = bytearray(make_image())
        image[4:8] = (len(image) + 1).to_bytes(4, "big")
        bad_length.write_bytes(image)
        result = run_validator(bad_length)
        assert result.returncode != 0
        assert "length mismatch" in result.stderr

        bad_checksum = root / "bad-checksum.bin"
        image = bytearray(make_image(b"\x01"))
        image[2:4] = (0).to_bytes(2, "big")
        bad_checksum.write_bytes(image)
        result = run_validator(bad_checksum)
        assert result.returncode != 0
        assert "checksum mismatch" in result.stderr

        bad_format = root / "bad-format.bin"
        image = bytearray(make_image())
        image[1] = 0x07
        bad_format.write_bytes(image)
        result = run_validator(bad_format)
        assert result.returncode != 0
        assert "unexpected FCode format" in result.stderr

    print("OpenBIOS VGA FCode validator tests: passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
