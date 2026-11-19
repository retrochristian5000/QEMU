#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""SDK-free regression checks for installed Darwin compiler-rt archive validation."""

from pathlib import Path
import struct
import tempfile
import unittest

from compiler_rt_archive_abi import ArchiveABIError, audit_archive, fat_slices


def macho(subtype, cpu=0x0100000C):
    return struct.pack("<8I", 0xFEEDFACF, cpu, subtype, 1, 0, 0, 0, 0)


def member(name, data):
    name = name.encode("utf-8")
    body = name + data
    header = (
        f"{'#1/' + str(len(name)):<16}{0:<12}{0:<6}{0:<6}{100644:<8}{len(body):<10}"
        + chr(96) + "\n"
    ).encode("ascii")
    assert len(header) == 60
    return header + body + (b"\n" if len(body) & 1 else b"")


def archive(entries):
    return b"!<arch>\n" + b"".join(member(name, data) for name, data in entries)


def universal(slices, fat64=False):
    entry_size = 32 if fat64 else 20
    out = bytearray(struct.pack(">II", 0xCAFEBABF if fat64 else 0xCAFEBABE,
                                len(slices)))
    entries = []
    at = 8 + len(slices) * entry_size
    for cpu, subtype, data in slices:
        at += (-at) % 4
        entries.append((cpu, subtype, at, len(data), 2))
        at += len(data)
    for cpu, subtype, start, size, align in entries:
        if fat64:
            out.extend(struct.pack(">IIQQII", cpu, subtype, start, size, align, 0))
        else:
            out.extend(struct.pack(">IIIII", cpu, subtype, start, size, align))
    for entry, (_, _, content) in zip(entries, slices):
        out.extend(bytes(entry[2] - len(out)))
        out.extend(content)
    return bytes(out)


class RuntimeArchiveTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "libclang_rt.osx.a"
        self.arm64 = archive([("plain.o", macho(0))])
        self.arm64e = archive([("auth.o", macho(0x80000002))])

    def audit(self, data, arch="arm64e"):
        self.path.write_bytes(data)
        return audit_archive(self.path, arch)

    def test_thin_arm64e(self):
        self.assertEqual(self.audit(self.arm64e), ["arm64e"])

    def test_mixed_member_subtype(self):
        data = archive([("good.o", macho(0x80000002)),
                        ("bad.o", macho(0x00000002))])
        with self.assertRaisesRegex(ArchiveABIError, "inconsistent arm64e ABI subtypes"):
            self.audit(data)

    def test_plain_arm64_does_not_satisfy_arm64e(self):
        with self.assertRaisesRegex(ArchiveABIError, "missing required arm64e"):
            self.audit(self.arm64)

    def test_fat32_and_fat64(self):
        slices = [(0x0100000C, 0, self.arm64),
                  (0x0100000C, 0x80000002, self.arm64e)]
        for fat64 in (False, True):
            with self.subTest(fat64=fat64):
                self.assertEqual(self.audit(universal(slices, fat64)),
                                 ["arm64", "arm64e"])

    def test_forged_fat_slice(self):
        data = universal([(0x0100000C, 0x80000002, self.arm64)], True)
        with self.assertRaisesRegex(ArchiveABIError, "disagrees with FAT table"):
            self.audit(data)

    def test_fat_bounds(self):
        data = universal([(0x0100000C, 0x80000002, self.arm64e)], True)
        with self.assertRaisesRegex(ArchiveABIError,
                                    "invalid universal arm64e slice bounds"):
            fat_slices(data[:-2], "corrupt.a")

    def test_kernel_archive_separate(self):
        self.path = self.path.with_name("libclang_rt.cc_kext.a")
        self.assertEqual(self.audit(archive([("kernel.o", macho(0xC0000002))])),
                         ["arm64e"])

    def test_invalid_member_data(self):
        with self.assertRaisesRegex(ArchiveABIError, "expected 64-bit Mach-O"):
            self.audit(archive([("bad.o", b"pretend-bitcode-file")]))


if __name__ == "__main__":
    unittest.main()
