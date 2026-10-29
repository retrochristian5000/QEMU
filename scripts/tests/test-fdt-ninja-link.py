#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit the Meson-generated Ninja link edge for QEMU's libfdt provider.

This reads an existing build graph; it never deletes or rebuilds the tree.
Use --internal for the pinned DTC wrap, --built to inspect its archive,
and --linked after a complete emulator link to verify the final executable.
"""

import argparse
import json
import pathlib
import re
import shutil
import subprocess


def fail(message):
    raise SystemExit("FDT Ninja link audit: " + message)


def build_option(build_dir, name):
    options = build_dir / "meson-info" / "intro-buildoptions.json"
    if not options.is_file():
        fail("missing Meson build options: " + str(options))
    for option in json.loads(options.read_text(encoding="utf-8")):
        if option.get("name") == name:
            return option.get("value")
    fail("Meson option not found: " + name)


def ninja_commands(build_dir, target):
    ninja = shutil.which("ninja")
    if not ninja:
        fail("Ninja is not installed")
    process = subprocess.run(
        [ninja, "-C", str(build_dir), "-t", "commands", target],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if process.returncode:
        fail("cannot inspect target " + target + ": " + process.stderr.strip())
    return process.stdout.splitlines()


def find_link_command(lines, target):
    # The macOS executable is linked as *-unsigned before entitlement signing.
    output_name = target + "-unsigned"
    for line in reversed(lines):
        if not re.search(r"(?:^|\s)-o\s+", line):
            continue
        if re.search(
            r"(?:^|\s)-o\s+(?:\S*/)?"
            + re.escape(output_name) + r"(?:\s|$)", line
        ) or re.search(
            r"(?:^|\s)-o\s+(?:\S*/)?"
            + re.escape(target) + r"(?:\s|$)", line
        ):
            return line
    fail("no final compiler/linker command for " + target)


def check_pinned_dtc():
    # A persistent Meson source checkout does not necessarily move when its
    # wrap file changes. Catch a stale DTC checkout before blaming Ninja.
    root = pathlib.Path(__file__).resolve().parents[2]
    wrap = root / "subprojects" / "dtc.wrap"
    match = re.search(
        r"(?m)^revision\s*=\s*([0-9a-fA-F]{40})\s*$",
        wrap.read_text(encoding="utf-8"),
    )
    if not match:
        fail("DTC wrap does not contain an immutable 40-character revision")
    checkout = root / "subprojects" / "dtc"
    revision = subprocess.run(
        ["git", "-C", str(checkout), "rev-parse", "HEAD"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if revision.returncode:
        fail("internal DTC checkout missing or unreadable: " + str(checkout))
    if revision.stdout.strip() != match.group(1):
        fail("DTC checkout is not at pinned wrap revision " + match.group(1)
             + "; update the Meson-owned DTC checkout, preserving your build")
    print("Verified: internal DTC checkout matches pinned wrap revision")


def check_archive(build_dir):
    archive = build_dir / "subprojects" / "dtc" / "libfdt" / "libfdt.a"
    if not archive.is_file():
        fail("internal libfdt archive not found: " + str(archive))
    # Check the actual archive members, not only Meson's intended source list.
    # fdt_nop_node lives in fdt_wip.c; a stale or incomplete archive could
    # otherwise pass the graph audit while omitting its implementation.
    ar = shutil.which("llvm-ar") or shutil.which("ar")
    if not ar:
        fail("ar/llvm-ar missing; cannot inspect libfdt archive members")
    members = subprocess.run(
        [ar, "-t", str(archive)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if members.returncode:
        fail("ar could not inspect internal libfdt: " + members.stderr.strip())
    if not any(pathlib.PurePath(name.strip()).name == "fdt_wip.c.o"
               for name in members.stdout.splitlines()):
        fail("internal libfdt.a omits fdt_wip.c.o (fdt_nop_node provider)")
    print("Verified: internal libfdt.a includes fdt_wip.c.o")
    nm = shutil.which("llvm-nm") or shutil.which("nm")
    if not nm:
        fail("nm/llvm-nm missing; cannot verify symbols")
    output = subprocess.run(
        [nm, "-g", str(archive)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if output.returncode:
        fail("nm could not inspect internal libfdt: " + output.stderr.strip())
    if not re.search(
        r"(?m)^\s*(?:[0-9a-fA-F]+\s+)?[A-TV-Z]\s+_?fdt_nop_node\s*$",
        output.stdout,
    ):
        fail("libfdt.a does not define fdt_nop_node; inspect fdt_wip.c compilation")
    print("Verified: internal libfdt.a defines fdt_nop_node")



def macho_object_abi(contents, label):
    """Read a thin, little-endian 64-bit ARM64 Mach-O object header.

    Unlike CPU-family guesses from uname or compiler identity, Mach-O
    cpusubtype identifies the ABI actually used to generate each object.
    """
    import struct

    if len(contents) < 12 or contents[:4] != b"\xcf\xfa\xed\xfe":
        fail(label + ": not a thin little-endian 64-bit Mach-O object")
    _magic, cpu_type, cpu_subtype = struct.unpack_from("<III", contents)
    if cpu_type != 0x0100000c:
        fail(label + ": expected ARM64 Mach-O CPU type, got "
             + hex(cpu_type))
    # Mach-O stores ARM64e pointer-authentication ABI version and kernel
    # flags in the high bits.  Do not mistake a versioned 0x80000002 object
    # for generic arm64 (0x00000000).
    base_subtype = cpu_subtype & 0x00ffffff
    if base_subtype in (0, 1):
        abi = "arm64"
    elif base_subtype == 2:
        abi = "arm64e"
    elif base_subtype == 12:
        abi = "arm64e.x1"
    else:
        fail(label + ": unknown ARM64 CPU subtype " + hex(cpu_subtype))
    return abi, cpu_subtype


def macho_minimum_macos(contents, label):
    """Extract the object/executable deployment floor from Mach-O commands."""
    import struct

    if len(contents) < 32 or contents[:4] != b"\xcf\xfa\xed\xfe":
        fail(label + ": expected a thin little-endian 64-bit Mach-O image")
    header = struct.unpack_from("<8I", contents)
    ncmds, sizecmds = header[4], header[5]
    end = 32 + sizecmds
    if end > len(contents):
        fail(label + ": Mach-O load commands exceed file size")
    offset = 32
    result = None
    for _ in range(ncmds):
        if offset + 8 > end:
            fail(label + ": truncated Mach-O load-command header")
        cmd, size = struct.unpack_from("<II", contents, offset)
        if size < 8 or offset + size > end:
            fail(label + ": malformed Mach-O load command")
        packed = None
        if cmd == 0x32 and size >= 24:  # LC_BUILD_VERSION
            platform, minimum = struct.unpack_from("<II", contents, offset + 8)
            if platform == 1:  # PLATFORM_MACOS
                packed = minimum
        elif cmd == 0x24 and size >= 16:  # LC_VERSION_MIN_MACOSX
            packed, = struct.unpack_from("<I", contents, offset + 8)
        if packed is not None:
            result = (packed >> 16, (packed >> 8) & 255, packed & 255)
        offset += size
    if offset != end:
        fail(label + ": inconsistent Mach-O load-command lengths")
    if result is None:
        fail(label + ": missing LC_BUILD_VERSION or LC_VERSION_MIN_MACOSX "
             "deployment metadata")
    return result


def macos_version_string(version):
    return ".".join(str(n) for n in version)


def check_macho_abi(build_dir, expected_arch=None):
    """Audit actual DTC archive members against QEMU's device-tree object."""
    archive = build_dir / "subprojects" / "dtc" / "libfdt" / "libfdt.a"
    qemu_object = build_dir / "libsystem.a.p" / "system_device_tree.c.o"
    if not archive.is_file() or not qemu_object.is_file():
        fail("Mach-O ABI check needs a built libfdt.a and "
             "libsystem.a.p/system_device_tree.c.o; build qemu-system-ppc "
             "before running --macho-abi")
    expected_abi, expected_subtype = macho_object_abi(
        qemu_object.read_bytes(), str(qemu_object)
    )
    consumer_min = macho_minimum_macos(
        qemu_object.read_bytes(), str(qemu_object)
    )
    if consumer_min < (11, 0, 0):
        fail("QEMU ARM64 object targets macOS " +
             macos_version_string(consumer_min) + "; minimum is 11.0")
    linked = build_dir / "qemu-system-ppc-unsigned"
    output_min = macho_minimum_macos(
        linked.read_bytes(), str(linked)
    ) if linked.is_file() else consumer_min
    if output_min < (11, 0, 0):
        fail("PowerPC emulator targets macOS " +
             macos_version_string(output_min) + "; ARM64 requires 11.0+")
    if expected_arch is not None and expected_abi != expected_arch:
        fail("QEMU device-tree object uses " + expected_abi +
             ", expected " + expected_arch + " (CPU subtype " +
             hex(expected_subtype) + ")")
    ar = shutil.which("llvm-ar") or shutil.which("ar")
    if not ar:
        fail("ar/llvm-ar missing; cannot inspect archive objects")
    members = subprocess.run(
        [ar, "-t", str(archive)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if members.returncode:
        fail("could not list libfdt.a: " + members.stderr.strip())
    names = [name.strip() for name in members.stdout.splitlines()
             if name.strip()]
    if not names or not any(pathlib.PurePath(name).name == "fdt_wip.c.o"
                            for name in names):
        fail("libfdt.a does not contain the fdt_wip.c.o provider")
    # BSD ar may list its Mach-O ranlib index as a pseudo-member.
    # GNU ar can expose analogous index or long-name table entries.
    # Neither contains object code, so audit the actual members only.
    metadata = {"__.SYMDEF", "__.SYMDEF SORTED", "/", "//", "/SYM64/"}
    objects = [name for name in names if name not in metadata]
    if not objects:
        fail("libfdt.a contains no object members")
    for name in objects:
        member = subprocess.run(
            [ar, "-p", str(archive), name],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if member.returncode:
            fail("could not read libfdt.a member " + name + ": " +
                 member.stderr.decode(errors="replace").strip())
        abi, subtype = macho_object_abi(member.stdout, name)
        member_min = macho_minimum_macos(member.stdout, name)
        if member_min < (11, 0, 0):
            fail("libfdt.a(" + name + ") targets macOS " +
                 macos_version_string(member_min) +
                 "; ARM64/ARM64e requires 11.0+")
        if member_min > output_min:
            fail("libfdt.a(" + name + ") requires macOS " +
                 macos_version_string(member_min) +
                 ", newer than QEMU executable deployment target " +
                 macos_version_string(output_min) +
                 "; align QEMU and DTC MACOSX_DEPLOYMENT_TARGET")
        if abi != expected_abi or (abi == "arm64e" and
                                   subtype != expected_subtype):
            fail("Mach-O ABI mismatch: QEMU device_tree.c.o is " +
                 expected_abi + "/" + hex(expected_subtype) +
                 " but libfdt.a(" + name + ") is " +
                 abi + "/" + hex(subtype) +
                 "; rebuild or reconfigure only the mismatched provider "
                 "with the selected -arch; do not add a duplicate symbol")
    print("Verified: " + str(len(names)) +
          " libfdt.a Mach-O objects match QEMU device_tree.c.o: " +
          expected_abi + "/" + hex(expected_subtype) +
          "; executable minimum macOS " + macos_version_string(output_min))


def check_linked_emulator(build_dir, target):
    # On Darwin the executable is linked as *-unsigned, then postprocessed
    # into the installed qemu-system-* file. Inspect the true link product.
    candidates = [build_dir / (target + "-unsigned"), build_dir / target]
    executable = next((p for p in candidates if p.is_file()), None)
    if executable is None:
        fail("emulator link output missing: " +
             ", ".join(str(p) for p in candidates))

    nm = shutil.which("llvm-nm") or shutil.which("nm")
    if not nm:
        fail("nm/llvm-nm missing; cannot inspect linked emulator")
    output = subprocess.run(
        [nm, "-g", str(executable)], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if output.returncode:
        fail("nm could not inspect linked emulator: " + output.stderr.strip())

    # A successful static link may dead-strip fdt_nop_node when no live
    # machine uses it. Do not require the symbol to survive in the Mach-O
    # global table: the graph and archive checks already verify its provider.
    # An unresolved import, however, is always invalid for -Dfdt=internal.
    symbols = re.findall(
        r"(?m)^\s*(?:[0-9a-fA-F]+\s+)?([A-Za-z])\s+_?fdt_nop_node\s*$",
        output.stdout,
    )
    if any(kind.upper() == "U" for kind in symbols):
        fail("linked emulator still imports undefined fdt_nop_node")
    if symbols:
        print("Verified: linked emulator retains fdt_nop_node:", executable)
    else:
        print("Verified: linked emulator has no unresolved fdt_nop_node "
              "(unused symbol may have been dead-stripped):", executable)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=pathlib.Path)
    parser.add_argument("--target", default="qemu-system-ppc")
    parser.add_argument("--internal", action="store_true",
                        help="require the pinned internal DTC subproject")
    parser.add_argument("--built", action="store_true",
                        help="also inspect the compiled internal archive with nm")
    parser.add_argument("--linked", action="store_true",
                        help="check the actual linked qemu-system-* binary (internal provider)")
    parser.add_argument("--macho-abi", action="store_true",
                        help="compare archived DTC Mach-O objects with QEMU's device-tree object")
    parser.add_argument("--expected-arch", choices=("arm64", "arm64e"),
                        help="require this Mach-O ABI with --macho-abi")
    args = parser.parse_args()
    build_dir = args.build_dir.resolve()
    if not (build_dir / "build.ninja").is_file():
        fail("build.ninja is missing; Meson has not configured this build directory")

    provider = build_option(build_dir, "fdt")
    if args.internal and provider != "internal":
        fail("expected -Dfdt=internal, but configured fdt=" + str(provider))

    commands = ninja_commands(build_dir, args.target)
    link = find_link_command(commands, args.target)
    archive_name = "subprojects/dtc/libfdt/libfdt.a"
    if args.internal:
        check_pinned_dtc()
        if archive_name not in link:
            fail("final emulator link omits the internal DTC libfdt.a archive")
        if not any("fdt_wip.c" in cmd for cmd in commands):
            fail("Ninja graph omits libfdt/fdt_wip.c (the fdt_nop_node definition)")
    elif "-lfdt" not in link and "libfdt." not in link:
        fail("final emulator link has no visible libfdt dependency")
    if args.built or args.linked:
        if not args.internal:
            fail("--built/--linked requires --internal to identify the provider")
        check_archive(build_dir)
    if args.expected_arch and not args.macho_abi:
        fail("--expected-arch requires --macho-abi")
    if args.macho_abi:
        if not args.internal:
            fail("--macho-abi requires --internal to identify the provider")
        check_macho_abi(build_dir, args.expected_arch)
    if args.linked:
        check_linked_emulator(build_dir, args.target)
    print("FDT Ninja link audit passed: provider=" + str(provider)
          + ", target=" + args.target)


if __name__ == "__main__":
    main()
