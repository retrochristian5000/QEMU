#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit installed Darwin compiler-rt static archives without rewriting ABI metadata."""

import argparse
from pathlib import Path
import struct

FAT32_MAGIC = b"\xca\xfe\xba\xbe"
FAT64_MAGIC = b"\xca\xfe\xba\xbf"
AR_MAGIC = b"!<arch>\n"
ARM64 = 0x0100000C
X86_64 = 0x01000007
ARM64E_USER_ABI0 = 0x80000002
CPU_CAPABILITY_MASK = 0xFF000000


class ArchiveABIError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ArchiveABIError(message)


def architecture(cpu, subtype):
    base = subtype & ~CPU_CAPABILITY_MASK
    if cpu == ARM64 and base == 2:
        return "arm64e"
    if cpu == ARM64 and base == 0:
        return "arm64"
    if cpu == X86_64 and base == 3:
        return "x86_64"
    if cpu == X86_64 and base == 8:
        return "x86_64h"
    return None


def archive_objects(data, name):
    require(data.startswith(AR_MAGIC), f"{name}: not a Darwin ar archive")
    cursor = len(AR_MAGIC)
    seen = 0
    while cursor < len(data):
        require(cursor + 60 <= len(data), f"{name}: truncated archive header")
        header = data[cursor:cursor + 60]
        require(header[58:] == bytes((96, 10)), f"{name}: malformed archive header")
        try:
            size = int(header[48:58].decode("ascii").strip())
            label = header[:16].decode("ascii").strip()
        except (ValueError, UnicodeError) as exc:
            raise ArchiveABIError(f"{name}: malformed archive member metadata") from exc
        require(size >= 0 and cursor + 60 + size <= len(data),
                f"{name}: truncated archive member")
        content = data[cursor + 60:cursor + 60 + size]
        if label.startswith("#1/"):
            try:
                name_length = int(label[3:])
            except ValueError as exc:
                raise ArchiveABIError(f"{name}: malformed BSD member name") from exc
            require(0 <= name_length <= size, f"{name}: invalid BSD member name")
            member_name = content[:name_length].rstrip(b"\0").decode("utf-8", "replace")
            content = content[name_length:]
        else:
            member_name = label.rstrip("/")
        cursor += 60 + size + (size & 1)
        if member_name.startswith("__.SYMDEF") or member_name in ("", "/", "//"):
            continue
        seen += 1
        require(len(content) >= 16, f"{name}({member_name}): truncated Mach-O object")
        require(struct.unpack_from("<I", content)[0] == 0xFEEDFACF,
                f"{name}({member_name}): expected 64-bit Mach-O object; "
                "unsupported bitcode or unexpected data must be checked separately")
        cpu, subtype, filetype = struct.unpack_from("<III", content, 4)
        require(filetype == 1, f"{name}({member_name}): not an MH_OBJECT member")
        yield member_name, cpu, subtype
    require(cursor == len(data), f"{name}: trailing archive data")
    require(seen > 0, f"{name}: no inspectable Mach-O members")


def fat_slices(data, name):
    if data[:4] not in (FAT32_MAGIC, FAT64_MAGIC):
        return [(None, None, data)]
    require(len(data) >= 8, f"{name}: truncated universal header")
    count = struct.unpack_from(">I", data, 4)[0]
    fat64 = data[:4] == FAT64_MAGIC
    entry_size = 32 if fat64 else 20
    require(0 < count <= (len(data) - 8) // entry_size,
            f"{name}: invalid universal architecture table")
    slices = []
    seen = set()
    ranges = []
    for i in range(count):
        offset = 8 + i * entry_size
        if fat64:
            cpu, subtype, start, size, align, reserved = struct.unpack_from(">IIQQII", data, offset)
            require(reserved == 0, f"{name}: FAT64 reserved field is not zero")
        else:
            cpu, subtype, start, size, align = struct.unpack_from(">IIIII", data, offset)
        arch = architecture(cpu, subtype)
        require(arch is not None, f"{name}: unsupported universal slice {cpu:#x}/{subtype:#x}")
        require(arch not in seen, f"{name}: duplicate universal slice {arch}")
        seen.add(arch)
        require(align <= 30 and start % (1 << align) == 0,
                f"{name}: misaligned universal {arch} slice")
        require(start >= 8 + count * entry_size and 0 < size <= len(data) - start,
                f"{name}: invalid universal {arch} slice bounds")
        ranges.append((start, start + size))
        slices.append((cpu, subtype, data[start:start + size]))
    ranges.sort()
    require(all(a[1] <= b[0] for a, b in zip(ranges, ranges[1:])),
            f"{name}: overlapping universal slices")
    return slices


def audit_archive(path, required_arch, require_selected=True):
    data = path.read_bytes()
    results = []
    for fat_cpu, fat_subtype, slice_data in fat_slices(data, path.name):
        seen_subtypes = set()
        member_arch = None
        for member, cpu, subtype in archive_objects(slice_data, path.name):
            arch = architecture(cpu, subtype)
            require(arch is not None,
                    f"{path.name}({member}): unknown CPU/subtype {cpu:#x}/{subtype:#x}")
            if fat_cpu is not None:
                require((cpu, subtype) == (fat_cpu, fat_subtype),
                        f"{path.name}({member}): Mach-O {cpu:#x}/{subtype:#x} "
                        f"disagrees with FAT table {fat_cpu:#x}/{fat_subtype:#x}")
            if member_arch is None:
                member_arch = arch
            require(arch == member_arch,
                    f"{path.name}({member}): mixed architectures in one archive")
            seen_subtypes.add(subtype)
            require(len(seen_subtypes) == 1,
                    f"{path.name}({member}): inconsistent {arch} ABI subtypes "
                    f"{', '.join(hex(x) for x in sorted(seen_subtypes))}")
            # Kernel-extension libraries have a separate ABI, not userland PAC.
            if arch == "arm64e" and "cc_kext" not in path.name:
                require(subtype == ARM64E_USER_ABI0,
                        f"{path.name}({member}): unsupported arm64e userland ABI "
                        f"{subtype:#x}; expected {ARM64E_USER_ABI0:#x}")
        results.append(member_arch)
    if require_selected:
        require(required_arch in results,
                f"{path.name}: missing required {required_arch} archive slice; "
                f"available: {', '.join(results)}")
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True,
                        help="installed Clang resource lib/darwin directory")
    parser.add_argument("--required-arch", choices=("arm64", "arm64e", "x86_64"),
                        required=True)
    args = parser.parse_args()
    root = args.directory
    require(root.is_dir(), f"missing compiler-rt Darwin runtime directory: {root}")
    files = sorted(root.glob("libclang_rt*.a"))
    require(files, f"no installed libclang_rt*.a archives in {root}")
    required = root / "libclang_rt.osx.a"
    require(required.is_file(), f"missing compiler-rt builtins archive: {required}")
    for archive in files:
        arches = audit_archive(archive, args.required_arch,
                               require_selected=archive == required)
        print(f"compiler-rt: {archive.name}: {', '.join(arches)}")
    print(f"compiler-rt: {len(files)} static archives verified for {args.required_arch}")


if __name__ == "__main__":
    try:
        main()
    except (ArchiveABIError, OSError) as exc:
        raise SystemExit(f"compiler-rt ABI audit failed: {exc}") from exc
