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

# The core exposes four programmable 32-bit timers.  Preserve their documented
# CONTROL/MODULUS/VALUE triplet without guessing CONTROL bit assignments.
for declaration in (
    "#define TRIMEDIA_NUM_TIMERS 4",
    "uint32_t control;",
    "uint32_t modulus;",
    "uint32_t value;",
    "TrimediaTimerState timers[TRIMEDIA_NUM_TIMERS];",
):
    assert declaration in cpu_h, f"missing TriMedia timer state: {declaration}"

# PNX15xx timer event-source selection is a four-bit field with these exact
# architectural source IDs.
expected_sources = {
    "TRIMEDIA_TIMER_SOURCE_CPU_CLOCK": 0,
    "TRIMEDIA_TIMER_SOURCE_PRESCALE": 1,
    "TRIMEDIA_TIMER_SOURCE_RESERVED": 2,
    "TRIMEDIA_TIMER_SOURCE_DATABREAK": 3,
    "TRIMEDIA_TIMER_SOURCE_INSTBREAK": 4,
    "TRIMEDIA_TIMER_SOURCE_CACHE1": 5,
    "TRIMEDIA_TIMER_SOURCE_CACHE2": 6,
    "TRIMEDIA_TIMER_SOURCE_VDI_CLK1": 7,
    "TRIMEDIA_TIMER_SOURCE_VDI_CLK2": 8,
    "TRIMEDIA_TIMER_SOURCE_VDO_CLK1": 9,
    "TRIMEDIA_TIMER_SOURCE_VDO_CLK2": 10,
    "TRIMEDIA_TIMER_SOURCE_AI_WS": 11,
    "TRIMEDIA_TIMER_SOURCE_AO_WS": 12,
    "TRIMEDIA_TIMER_SOURCE_GPIO_TIMER0": 13,
    "TRIMEDIA_TIMER_SOURCE_GPIO_TIMER1": 14,
    "TRIMEDIA_TIMER_SOURCE_REFERENCE_CLOCK": 15,
}
for name, value in expected_sources.items():
    assert f"{name} = {value}" in cpu_h, f"wrong/missing timer source {name}"

# PNX15xx maps TIMER1/2/3/SYSTIMER to VIC sources 5/6/7/8.
for name, value in (
    ("TRIMEDIA_IRQ_TIMER1", 5),
    ("TRIMEDIA_IRQ_TIMER2", 6),
    ("TRIMEDIA_IRQ_TIMER3", 7),
    ("TRIMEDIA_IRQ_SYSTIMER", 8),
):
    assert f"{name} = {value}" in cpu_h, f"wrong/missing timer IRQ {name}"

# All of these registers belong to resettable CPU architectural state.
reset_marker = cpu_h.index("struct {} end_reset_fields;")
for declaration in expected_state + ("TrimediaTimerState timers[TRIMEDIA_NUM_TIMERS];",):
    assert cpu_h.index(declaration) < reset_marker, (
        f"TriMedia register is outside reset state: {declaration}"
    )

# State dumps are the first debugger/diagnostic visibility for this target.
for name in ("pcsw", "dpc", "spc", "excvec", "cccount"):
    assert f"env->{name}" in cpu_c, f"CPU dump does not expose {name}"
for name in ("control", "modulus", "value"):
    assert f"timer->{name}" in cpu_c, f"CPU dump does not expose timer {name}"

print("TriMedia architectural register and timer state: verified")
