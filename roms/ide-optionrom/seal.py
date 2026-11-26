#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate and seal an ISA IDE option ROM and its PnP expansion header."""
import os
import pathlib
import struct
import sys
import tempfile


def seal(raw: bytes) -> bytes:
    if len(raw) < 512 or raw[:2] != b'\x55\xaa':
        raise ValueError('missing option-ROM signature')
    if len(raw) != raw[2] * 512 or raw[-1]:
        raise ValueError('invalid option-ROM length or reserved checksum byte')
    pci, pnp = struct.unpack_from('<HH', raw, 0x18)
    if pci or pnp < 0x1c or pnp + 32 >= len(raw):
        raise ValueError('invalid ISA option-ROM header offsets')
    if raw[pnp:pnp + 6] != b'$PnP\x01\x02':
        raise ValueError('invalid PnP expansion header')
    bcv, dv, bev = struct.unpack_from('<HHH', raw, pnp + 0x16)
    if not pnp + 32 <= bcv < len(raw) - 1 or dv or bev:
        raise ValueError('invalid boot connection vector')
    data = bytearray(raw)
    data[pnp + 9] = 0
    data[pnp + 9] = -sum(data[pnp:pnp + 32]) & 0xff
    data[-1] = -sum(data) & 0xff
    return bytes(data)


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit('usage: seal.py INPUT OUTPUT')
    source, output = map(pathlib.Path, sys.argv[1:])
    try:
        data = seal(source.read_bytes())
        with tempfile.NamedTemporaryFile(dir=output.parent, delete=False) as tmp:
            name = tmp.name
            try:
                tmp.write(data)
                tmp.flush()
                os.fchmod(tmp.fileno(), 0o644)
                tmp.close()
                os.replace(name, output)
            finally:
                if os.path.exists(name):
                    os.unlink(name)
    except (ValueError, OSError) as error:
        sys.exit(f'error: IDE option ROM: {error}')


if __name__ == '__main__':
    main()
