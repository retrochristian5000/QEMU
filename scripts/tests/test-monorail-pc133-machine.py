#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Protect the historical boundaries of the Monorail PC 133 QEMU profile."""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "hw/i386/pc_piix.c"
DOCUMENT = ROOT / "docs/system/i386/pc.rst"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--qemu", type=Path, help="built i386 QEMU for machine registration smoke test")
args = parser.parse_args()

source = SOURCE.read_text(encoding="utf-8")
doc = DOCUMENT.read_text(encoding="utf-8")
profile = source.split("// WHP_MONORAIL_PC133_BEGIN", 1)[1].split(
    "// WHP_MONORAIL_PC133_END", 1
)[0]

required = (
    'DEFINE_PC_MACHINE(monorail_pc133, "monorail-pc133"',
    'pc_i440fx_machine_options(m);',
    'pc_i440fx_init(machine);',
    'm->family = "monorail";',
    'm->default_cpu_type = X86_CPU_TYPE_NAME("pentium");',
    'm->default_ram_size = 16 * MiB;',
    'machine->ram_size < 16 * MiB || machine->ram_size > 80 * MiB',
    'm->max_cpus = 1;',
    'm->has_hotpluggable_cpus = false;',
    'm->default_display = "std";',
)
for item in required:
    assert item in profile, f"missing Monorail PC 133 contract: {item}"
assert 'm->default_nic = "ne2k_isa";' in profile
assert "Chips & Technologies" in doc
assert "not yet a component-accurate" in doc
assert "Series 8005" in doc
assert "original BIOS ROM" in doc
assert "WHP_MONORAIL_PC133_BEGIN" in source
assert "WHP_MONORAIL_PC133_END" in source

if args.qemu is not None:
    binary = args.qemu.resolve(strict=True)
    listing = subprocess.run(
        [str(binary), "-machine", "help"],
        text=True, capture_output=True, check=True, timeout=20,
    )
    assert "monorail-pc133" in listing.stdout, (
        "Monorail machine was not registered in the i386 binary"
    )

    # The machine-specific RAM restriction must run before BIOS boot.
    invalid = subprocess.run(
        [str(binary), "-machine", "monorail-pc133",
         "-m", "8M", "-display", "none", "-nic", "none",
         "-S"],
        text=True, capture_output=True, timeout=20,
    )
    assert invalid.returncode != 0
    assert "monorail-pc133 requires 16-80 MiB of RAM" in invalid.stderr, (
        invalid.stderr
    )

print("Monorail PC 133 machine profile: verified")
