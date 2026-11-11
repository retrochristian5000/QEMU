#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check LLVM ar/ranlib ARM64e Mach-O member integrity and Darwin archive index.

Portable cross-compile tests need no Apple SDK; --sdkroot adds an Apple-ld link
smoke proving actual archive member extraction and the final Mach-O subtype.
"""
import argparse
from collections import Counter
from pathlib import Path
import struct
import subprocess
import tempfile

CPU_ARM64 = 0x0100000c
SUBTYPE_ARM64E_ABI0 = 0x80000002


def run(args):
    p = subprocess.run(args, capture_output=True, text=True, check=False)
    if p.returncode:
        raise RuntimeError(f"{args!r}: {p.stderr}")
    return p.stdout


def exports(data):
    assert len(data) >= 32, "truncated Mach-O member"
    magic, cpu, subtype, filetype, ncmds, cmdsize = struct.unpack_from("<6I", data)
    assert (magic, cpu, subtype, filetype) == (
        0xfeedfacf, CPU_ARM64, SUBTYPE_ARM64E_ABI0, 1
    ), f"wrong ARM64e ABI header: cpu={cpu:#x} subtype={subtype:#x} type={filetype}"
    assert 32 + cmdsize <= len(data), "truncated load commands"
    pos = 32
    symtab = None
    for _ in range(ncmds):
        assert pos + 8 <= 32 + cmdsize
        cmd, size = struct.unpack_from("<II", data, pos)
        assert size >= 8 and pos + size <= 32 + cmdsize
        if cmd == 2:  # LC_SYMTAB
            assert size >= 24 and symtab is None
            symtab = struct.unpack_from("<4I", data, pos + 8)
        pos += size
    assert pos == 32 + cmdsize and symtab is not None, "missing LC_SYMTAB"
    symoff, nsyms, stroff, strsize = symtab
    assert symoff + nsyms * 16 <= len(data) and stroff + strsize <= len(data)
    result = []
    for i in range(nsyms):
        strx, flags, _, _, _ = struct.unpack_from("<IBBHQ", data, symoff + i * 16)
        if flags & 0xe0 or not flags & 1 or (flags & 0xe) == 0:
            continue
        assert strx < strsize
        end = data.find(b"\0", stroff + strx, stroff + strsize)
        assert end >= 0
        result.append(data[stroff + strx:end].decode("utf-8"))
    return result


def members(data):
    assert data.startswith(b"!<arch>\n"), "not a regular BSD/Darwin archive"
    pos = 8
    out = []
    while pos < len(data):
        assert pos + 60 <= len(data), "truncated ar header"
        hdr = data[pos:pos + 60]
        assert hdr[58:60] == bytes((96, 10)), "invalid ar header terminator"
        raw = hdr[:16].decode("ascii").strip()
        size = int(hdr[48:58].decode("ascii").strip())
        assert pos + 60 + size <= len(data), "truncated ar member"
        body = data[pos + 60:pos + 60 + size]
        if raw.startswith("#1/"):
            name_len = int(raw[3:])
            assert name_len <= size
            name = body[:name_len].rstrip(b"\0").decode("utf-8")
            body = body[name_len:]
        else:
            name = raw.rstrip("/")
        out.append((pos, name, body))
        pos += 60 + size + size % 2
    assert pos == len(data), "trailing/incomplete archive data"
    return out


def audit(data, exact_bytes=None, complete_index=True):
    entries = members(data)
    indexes = [body for _, name, body in entries
               if name in ("__.SYMDEF", "__.SYMDEF SORTED")]
    assert len(indexes) == 1, "expected exactly one Darwin BSD ranlib index"
    index = indexes[0]
    count = struct.unpack_from("<I", index)[0]
    assert count % 8 == 0 and 8 + count <= len(index)
    names_len = struct.unpack_from("<I", index, 4 + count)[0]
    names_off = 8 + count
    assert names_off + names_len <= len(index), "truncated ranlib names"
    objects = {offset: (name, data) for offset, name, data in entries
               if not name.startswith("__.SYMDEF")}
    assert objects, "empty object archive"
    declared = Counter()
    for offset, (name, body) in objects.items():
        if exact_bytes is not None and name in exact_bytes:
            assert body == exact_bytes[name], f"{name}: object bytes mutated by ar"
        for sym in exports(body):
            declared[(sym, offset)] += 1
    indexed = Counter()
    for i in range(count // 8):
        strx, off = struct.unpack_from("<II", index, 4 + i * 8)
        assert off in objects, "ranlib points outside an object member"
        assert strx < names_len
        last = index.find(b"\0", names_off + strx, names_off + names_len)
        assert last >= 0, "unterminated ranlib symbol"
        indexed[(index[names_off + strx:last].decode("utf-8"), off)] += 1
    assert indexed, "Darwin ranlib has no indexed exports"
    assert not indexed - declared, f"stale/wrong ranlib symbols: {indexed-declared}"
    if complete_index:
        assert declared == indexed, f"missing ranlib symbols: {declared-indexed}"
    return entries


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--clang")
    ap.add_argument("--ar")
    ap.add_argument("--ranlib")
    ap.add_argument("--objdump")
    ap.add_argument("--sdkroot")
    ap.add_argument("--deployment-target", default="13.0")
    ap.add_argument("--audit-archive", type=Path)
    args = ap.parse_args()
    if args.audit_archive:
        entries = audit(args.audit_archive.read_bytes(), complete_index=False)
        print(f"ARM64e Darwin archive: {len(entries)-1} Mach-O members indexed")
        return
    assert args.clang and args.ar and args.ranlib
    if args.sdkroot:
        assert args.objdump, "--objdump is required for final link validation"
    with tempfile.TemporaryDirectory(prefix="whp-arm64e-ar-") as tmp:
        root = Path(tmp)
        objs = []
        for name, key, diversity in (("first", "ia", 42),
                                     ("second", "db", 65535)):
            src = root / (name + ".s")
            src.write_text(
                ".text\n.globl _whp_ar_" + name + "\n_whp_ar_" + name +
                ":\n ret\n.data\n.p2align 3\n.quad _whp_ar_" + name +
                f"@AUTH({key},{diversity},addr)\n", encoding="utf-8")
            obj = root / (name + ".o")
            run([args.clang, "-target", "arm64e-apple-macosx13.0",
                 "-c", str(src), "-o", str(obj)])
            objs.append(obj)
        raw = {p.name: p.read_bytes() for p in objs}
        originals = (root / "one.a", root / "two.a")
        for lib in originals:
            run([args.ar, "--format=darwin", "rcs", str(lib),
                 *map(str, objs)])
            run([args.ranlib, str(lib)])
            audit(lib.read_bytes(), raw)
        assert originals[0].read_bytes() == originals[1].read_bytes(), (
            "Darwin archive creation was nondeterministic")

        # Updating a member must refresh symbol offsets and names.
        src = root / "first.s"
        src.write_text(src.read_text().replace("_whp_ar_first",
                                                "_whp_ar_first_new"))
        run([args.clang, "-target", "arm64e-apple-macosx13.0",
             "-c", str(src), "-o", str(objs[0])])
        run([args.ar, "r", str(originals[1]), str(objs[0])])
        run([args.ranlib, str(originals[1])])
        updated = dict(raw)
        updated[objs[0].name] = objs[0].read_bytes()
        audit(originals[1].read_bytes(), updated)
        assert b"_whp_ar_first_new" in originals[1].read_bytes()
        assert b"_whp_ar_first\0" not in originals[1].read_bytes(), (
            "stale symbol survived archive member replacement")

        # Generic ar allows mixing CPUs; the ABI checker must reject it.
        plain = root / "plain.s"
        plain.write_text(".text\n.globl _whp_plain\n_whp_plain:\n ret\n")
        obj = root / "plain.o"
        run([args.clang, "-target", "arm64-apple-macosx13.0", "-c",
             str(plain), "-o", str(obj)])
        mixed = root / "mixed.a"
        run([args.ar, "--format=darwin", "rcs", str(mixed),
             str(objs[0]), str(obj)])
        run([args.ranlib, str(mixed)])
        try:
            audit(mixed.read_bytes())
        except AssertionError as error:
            assert "wrong ARM64e ABI header" in str(error), str(error)
        else:
            raise AssertionError("mixed ARM64/ARM64e archive passed ABI audit")

        # Corrupt a BSD ranlib offset without damaging any Mach-O object.
        broken = bytearray(originals[0].read_bytes())
        struct.pack_into("<I", broken, members(broken)[0][0] + 60 + 20, 0)
        try:
            audit(broken)
        except AssertionError as error:
            assert "ranlib points outside" in str(error), str(error)
        else:
            raise AssertionError("corrupt Darwin symbol index was accepted")

        if args.sdkroot:
            src = root / "main.c"
            src.write_text(
                "extern void whp_ar_first(void),whp_ar_second(void);\n"
                "int main(void){whp_ar_first();whp_ar_second();return 0;}\n")
            caller = root / "main.o"
            run([args.clang, "-target", "arm64e-apple-macosx13.0",
                 "-c", str(src), "-o", str(caller)])
            binary = root / "linked"
            # Apple ld is intentional: LLD has a separate PAC admission gate.
            run([args.clang, "-arch", "arm64e", "-isysroot", args.sdkroot,
                 "-mmacosx-version-min=" + args.deployment_target,
                 str(caller), str(originals[0]), "-o", str(binary)])
            table = run([args.objdump, "--syms", str(binary)])
            assert "_whp_ar_first" in table and "_whp_ar_second" in table, (
                "linker did not extract both indexed archive members")
            assert struct.unpack_from("<3I", binary.read_bytes()) == (
                0xfeedfacf, CPU_ARM64, SUBTYPE_ARM64E_ABI0
            ), "final binary lost ARM64e ABI subtype"
    print("ARM64e llvm-ar: member bytes, Mach-O ABI, ranlib mapping, "
          "incremental replacement, mixed-ABI rejection and corruption "
          "guards passed" + ("; Apple linked" if args.sdkroot
                            else "; SDK-free cross objects only"))


if __name__ == "__main__":
    main()
