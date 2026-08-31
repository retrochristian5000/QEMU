#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
cpu_h = (ROOT / "target/trimedia/cpu.h").read_text(encoding="utf-8")
cpu_c = (ROOT / "target/trimedia/cpu.c").read_text(encoding="utf-8")

# TM3260 core architectural state: keep the first register slice explicit.
expected_state = (
    "uint32_t pc;",
    "uint32_t pcsw;",
    "uint32_t dpc;",
    "uint32_t spc;",
    "uint32_t excvec;",
    "uint64_t cccount;",
)
for declaration in expected_state:
    assert declaration in cpu_h, f"missing TriMedia state field: {declaration}"

# All of these registers belong to resettable CPU architectural state.
reset_marker = cpu_h.index("struct {} end_reset_fields;")
for declaration in expected_state:
    assert cpu_h.index(declaration) < reset_marker, (
        f"TriMedia register is outside reset state: {declaration}"
    )

# State dumps are the first debugger/diagnostic visibility for this target.
for name in ("pcsw", "dpc", "spc", "excvec", "cccount"):
    assert f"env->{name}" in cpu_c, f"CPU dump does not expose {name}"

print("TriMedia architectural register state: verified")
