#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit the Meson-generated Ninja link edge for QEMU's libfdt provider.

This reads an existing build graph; it never deletes or rebuilds the tree.
Use --internal for the pinned DTC wrap and --built after a successful build
to verify that the archive actually defines fdt_nop_node.
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
        r"(?m)^revision\\s*=\\s*([0-9a-fA-F]{40})\\s*$",
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("build_dir", type=pathlib.Path)
    parser.add_argument("--target", default="qemu-system-ppc")
    parser.add_argument("--internal", action="store_true",
                        help="require the pinned internal DTC subproject")
    parser.add_argument("--built", action="store_true",
                        help="also inspect the compiled internal archive with nm")
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
    if args.built:
        if not args.internal:
            fail("--built requires --internal to identify the built archive")
        check_archive(build_dir)
    print("FDT Ninja link audit passed: provider=" + str(provider)
          + ", target=" + args.target)


if __name__ == "__main__":
    main()
