#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Synthetic MacBinary NDIF regression; --qemu-img enables runtime checks."""

import argparse
import json
import struct
import subprocess
import tempfile
from pathlib import Path


def bcem(chunks, blocks, segmented=0):
    h = bytearray(128)
    struct.pack_into(">HH", h, 0, 10, 0)
    h[4] = 4
    h[5:9] = b"Test"
    struct.pack_into(">III", h, 68, blocks, 16, 0)
    struct.pack_into(">I", h, 84, segmented)
    struct.pack_into(">I", h, 124, len(chunks))
    for sector, kind, pos, size in chunks:
        h += sector.to_bytes(3, "big") + bytes([kind])
        h += struct.pack(">II", pos, size)
    return bytes(h)


def resource(payload):
    f = bytearray(260)
    struct.pack_into(">IIII", f, 0, 256, 16, len(payload) + 4, 64)
    struct.pack_into(">HH", f, 40, 28, 50)
    f[46:50] = b"bcem"
    struct.pack_into(">HH", f, 50, 0, 10)
    struct.pack_into(">H", f, 54, 128)
    struct.pack_into(">I", f, 256, len(payload))
    return bytes(f) + payload


def mb(data, fork):
    h = bytearray(128)
    h[1] = 4
    h[2:6] = b"Test"
    h[65:69] = b"APPL"
    h[69:73] = b"dCpy"
    struct.pack_into(">II", h, 83, len(data), len(fork))
    h += data
    h += bytes(-len(h) % 128)
    return bytes(h) + fork


def cmd(tool, *args, good=True):
    p = subprocess.run([str(tool), *map(str, args)], capture_output=True,
                       text=True, check=False)
    assert (p.returncode == 0) == good, (
        f"qemu-img exit {p.returncode}: {args}: {p.stderr}"
    )
    return p.stdout


def integration(tool):
    with tempfile.TemporaryDirectory(prefix="qemu-smi-") as td:
        path = Path(td)
        raw = bytes(range(256)) * 2
        src = path / "sample.smi.bin"
        dst = path / "disk.raw"

        # A 512-byte raw chunk followed by one zero sector.
        chunks = [(0, 2, 0, 512), (1, 0, 0, 0), (2, 255, 0, 0)]
        src.write_bytes(mb(raw, resource(bcem(chunks, 2))))
        info = json.loads(cmd(tool, "info", "--output=json", src))
        assert info["format"] == "smi"
        assert info["virtual-size"] == 1024
        cmd(tool, "convert", "-f", "smi", "-O", "raw", src, dst)
        assert dst.read_bytes() == raw + bytes(512)

        # ADC literal runs output 128 bytes each.
        compressed = b"".join(b"\xff" + raw[i:i + 128]
                             for i in range(0, 512, 128))
        chunks = [(0, 131, 0, len(compressed)), (1, 255, 0, 0)]
        src.write_bytes(mb(compressed, resource(bcem(chunks, 1))))
        cmd(tool, "convert", "-f", "smi", "-O", "raw", src, dst)
        assert dst.read_bytes() == raw

        # This ADC copy points before any decoded output and must fail.
        src.write_bytes(mb(b"\x00\x00", resource(bcem(
            [(0, 131, 0, 2), (1, 255, 0, 0)], 1))))
        cmd(tool, "convert", "-f", "smi", "-O", "raw",
            src, dst, good=False)

        # No resource fork: never interpret an executable as disk sectors.
        src.write_bytes(mb(raw, b""))
        cmd(tool, "info", "-f", "smi", src, good=False)

        # No KenCode/segmented fallback to raw.
        src.write_bytes(mb(raw, resource(bcem(
            [(0, 128, 0, 512), (1, 255, 0, 0)], 1))))
        cmd(tool, "info", "-f", "smi", src, good=False)
        src.write_bytes(mb(raw, resource(bcem(
            [(0, 2, 0, 512), (1, 255, 0, 0)], 1, segmented=1))))
        cmd(tool, "info", "-f", "smi", src, good=False)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu-img", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    s = (root / "block/smi.c").read_text(encoding="utf-8")
    meson = (root / "block/meson.build").read_text(encoding="utf-8")
    assert "'smi.c'" in meson
    # Regressions observed in Werror PowerPC CI: this tree's coroutine API
    # takes CoMutex*, and qemu/bswap.h provides lduw_be_p/ldl_be_p.
    # Implicit function declarations and an undefined lock type must not
    # leak into the disk image reader again.
    bswap = (root / "include/qemu/bswap.h").read_text(encoding="utf-8")
    coroutine = (root / "include/qemu/coroutine-core.h").read_text(
        encoding="utf-8")
    assert "CoMutex lock;" in s
    assert "QemuCoMutex" not in s
    for name, header in (("lduw_be_p", bswap), ("ldl_be_p", bswap),
                         ("qemu_co_mutex_init", coroutine),
                         ("qemu_co_mutex_lock", coroutine),
                         ("qemu_co_mutex_unlock", coroutine)):
        assert name in header, f"missing QEMU API: {name}"
        assert name + "(" in s, f"missing SMI call: {name}"
    assert "ld_be16(" not in s and "ld_be32(" not in s
    assert "rsrc_size" not in s
    for required in ("smi_bcem(", "smi_adc_decode(", "smi_range(",
                     "bdrv_apply_auto_read_only", "SMI_FORK_MAX",
                     "SMI_CHUNK_MAX", "chunk->type == 131",
                     ".format_name = \"smi\""):
        assert required in s, required
    sample = mb(bytes(512), resource(bcem(
        [(0, 2, 0, 512), (1, 255, 0, 0)], 1)))
    assert sample[0] == 0 and sample[1] == 4
    assert int.from_bytes(sample[83:87], "big") == 512
    if args.qemu_img:
        integration(args.qemu_img)
    print("SMI MacBinary NDIF image contracts: verified")


if __name__ == "__main__":
    main()
