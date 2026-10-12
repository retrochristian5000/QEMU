#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Deterministic ARM64/arm64e Mach-O archive/consumer ABI regression test.

Construct tiny Mach-O object headers and package them with the host ar tool.
The actual compiler and linker are tested by the macOS CI build separately.
No project sources or existing build outputs are changed.
"""

import importlib.util
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
AUDIT = ROOT / "scripts/tests/test-fdt-ninja-link.py"
SPEC = importlib.util.spec_from_file_location("whp_fdt_audit", AUDIT)
AUDITOR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUDITOR)


def macho(subtype):
    # MH_MAGIC_64, CPU_TYPE_ARM64, subtype, MH_OBJECT and empty commands.
    return struct.pack("<8I", 0xfeedfacf, 0x0100000C, subtype,
                       1, 0, 0, 0, 0)


def run_case(label, consumer, provider, second, expected, fails=False):
    with tempfile.TemporaryDirectory(prefix="whp-fdt-abi-") as folder:
        build = Path(folder)
        object_dir = build / "libsystem.a.p"
        object_dir.mkdir()
        (object_dir / "system_device_tree.c.o").write_bytes(macho(consumer))

        lib_dir = build / "subprojects/dtc/libfdt"
        lib_dir.mkdir(parents=True)
        first = build / "fdt_wip.c.o"
        other = build / "fdt_rw.c.o"
        first.write_bytes(macho(provider))
        other.write_bytes(macho(second))
        archive = lib_dir / "libfdt.a"
        subprocess.run([AR, "rcs", str(archive), str(first), str(other)],
                       check=True, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE)
        try:
            AUDITOR.check_macho_abi(build, expected)
        except SystemExit as exc:
            if not fails:
                raise AssertionError(label + " unexpectedly rejected: " +
                                     str(exc)) from exc
            if "ABI mismatch" not in str(exc):
                raise AssertionError(label + " gave unrelated error: " +
                                     str(exc)) from exc
        else:
            if fails:
                raise AssertionError(label + " accepted incompatible objects")


AR = shutil.which("llvm-ar") or shutil.which("ar")
if not AR:
    raise SystemExit("llvm-ar/ar required for Mach-O fixture archive tests")

# A compiler's executable ABI must never substitute for the emitted object's.
run_case("arm64", 0x0, 0x0, 0x0, "arm64")
# LLVM's versioned pointer-authentication ABI 0 subtype.
run_case("arm64e", 0x80000002, 0x80000002, 0x80000002, "arm64e")
run_case("mixed fdt_wip provider", 0x80000002, 0x0, 0x80000002,
         "arm64e", fails=True)
run_case("mixed secondary archive member", 0x80000002, 0x80000002, 0x0,
         "arm64e", fails=True)
run_case("arm64 consumer of arm64e", 0x0, 0x80000002, 0x0,
         "arm64", fails=True)
run_case("unversioned arm64e mixed with versioned", 0x80000002, 0x2,
         0x80000002, "arm64e", fails=True)
print("FDT Mach-O ABI archive/consumer regression tests passed")
