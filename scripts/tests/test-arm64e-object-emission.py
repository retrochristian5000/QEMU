#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit Clang's emitted ARM64e Mach-O .o files before passing them to LLD."""

import argparse
from pathlib import Path
import struct
import subprocess
import tempfile

ASM = """\
.text
.globl _whp_target
_whp_target:
 ret
.data
.p2align 3
.quad _whp_target@AUTH(ia,42,addr)
.quad _whp_target@AUTH(ib,513)
.quad _whp_target@AUTH(da,7,addr)
.quad _whp_target@AUTH(db,65535)
.quad _whp_target
"""
C = """\
typedef int (*callback_t)(int);
extern int whp_external(int);
callback_t whp_stored_callback = whp_external;
int whp_call(callback_t cb, int value) { return cb(value); }
"""
CPP = """\
struct WhpBase { virtual int run(int); virtual ~WhpBase(); };
int WhpBase::run(int n) { return n + 42; }
WhpBase::~WhpBase() {}
extern "C" int whp_virtual(WhpBase *p, int n) { return p->run(n); }
"""


def u32(data, offset):
    return struct.unpack_from("<I", data, offset)[0]


def run(argv):
    p = subprocess.run(argv, text=True, capture_output=True, check=False)
    if p.returncode:
        raise RuntimeError(f"{argv!r}: {p.stderr}")
    return p.stdout


def parse_object(path, subtype):
    data = path.read_bytes()
    assert len(data) >= 32
    assert tuple(u32(data, k) for k in (0, 4, 8, 12)) == (
        0xFEEDFACF, 0x0100000C, subtype, 1), f"{path}: wrong Mach-O ABI"
    pos, end = 32, 32 + u32(data, 20)
    assert end <= len(data)
    sections = {}
    for _ in range(u32(data, 16)):
        assert pos + 8 <= end
        cmd, size = struct.unpack_from("<II", data, pos)
        assert size >= 8 and pos + size <= end
        if cmd == 0x19:  # LC_SEGMENT_64
            count = u32(data, pos + 64)
            assert pos + 72 + count * 80 <= pos + size
            for idx in range(count):
                sec = pos + 72 + 80 * idx
                name = data[sec:sec + 16].split(b"\0", 1)[0]
                seg = data[sec + 16:sec + 32].split(b"\0", 1)[0]
                file_off, rel_off, rel_count = (u32(data, sec + k)
                                                for k in (48, 56, 60))
                assert rel_off + rel_count * 8 <= len(data)
                relocs = {}
                for i in range(rel_count):
                    off, info = struct.unpack_from("<II", data, rel_off + i * 8)
                    relocs[off] = (info >> 28, (info >> 25) & 3,
                                    (info >> 24) & 1, (info >> 27) & 1)
                sections[(seg, name)] = (file_off, relocs)
        pos += size
    assert pos == end
    return data, sections


def emit(cc, target, source, output, *extra):
    run([cc, "-target", target, "-O0", "-c", str(source), "-o",
         str(output), *extra])
    return parse_object(output, 0x80000002 if target.startswith("arm64e-") else 0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clang", required=True)
    ap.add_argument("--clangxx", required=True)
    ap.add_argument("--objdump", required=True)
    args = ap.parse_args()
    with tempfile.TemporaryDirectory(prefix="whp-arm64e-objects-") as tmp:
        root = Path(tmp)
        for name, source in (("auth.s", ASM), ("callback.c", C),
                             ("virtual.cc", CPP)):
            (root / name).write_text(source, encoding="utf-8")

        data, sections = emit(args.clang, "arm64e-apple-macosx13.0",
                              root / "auth.s", root / "auth.o")
        fileoff, relocs = sections[(b"__DATA", b"__data")]
        assert len(relocs) == 5
        expected = ((0, 42, 1), (1, 513, 0), (2, 7, 1), (3, 65535, 0))
        for i, (key, div, addr) in enumerate(expected):
            assert relocs[i * 8] == (11, 3, 0, 1)
            word = struct.unpack_from("<Q", data, fileoff + i * 8)[0]
            assert (word >> 63, (word >> 51) & 0xfff, word & 0xffffffff) == (1, 0, 0)
            assert (((word >> 49) & 3), ((word >> 32) & 65535),
                    ((word >> 48) & 1)) == (key, div, addr)
        assert relocs[32] == (0, 3, 0, 1)

        _, csec = emit(args.clang, "arm64e-apple-macosx13.0",
                       root / "callback.c", root / "callback-arm64e.o")
        assert [r[0] for r in csec[(b"__DATA", b"__data")][1].values()] == [11]
        e_dis = run([args.objdump, "-d", str(root / "callback-arm64e.o")]).lower()
        assert "blraa" in e_dis

        _, asec = emit(args.clang, "arm64-apple-macosx13.0",
                       root / "callback.c", root / "callback-arm64.o")
        assert [r[0] for r in asec[(b"__DATA", b"__data")][1].values()] == [0]
        a_dis = run([args.objdump, "-d", str(root / "callback-arm64.o")]).lower()
        assert "blr" in a_dis and "blraa" not in a_dis

        _, cppsec = emit(args.clangxx, "arm64e-apple-macosx13.0",
                         root / "virtual.cc", root / "virtual-arm64e.o",
                         "-std=c++17")
        count = sum(r[0] == 11 for (seg, name), (_, rels) in cppsec.items()
                    for r in rels.values() if name == b"__const")
        assert count >= 3, f"C++ vtable lost authenticated pointers: {count}"
        v_dis = run([args.objdump, "-d", str(root / "virtual-arm64e.o")]).lower()
        assert "blraa" in v_dis
    print("ARM64e object emission: header, PAC, C callbacks, C++ virtual calls, ARM64 control passed")


if __name__ == "__main__":
    main()
