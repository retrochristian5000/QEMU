#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify PPC TCG clock helpers preserve icount IO boundaries."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
translator = (ROOT / "target/ppc/translate.c").read_text(encoding="utf-8")
timebase = (ROOT / "hw/ppc/ppc.c").read_text(encoding="utf-8")
interface = (ROOT / "include/exec/translator.h").read_text(encoding="utf-8")


def body(source: str, name: str) -> str:
    # These PPC helpers have no nested scopes; reject missing definitions.
    match = re.search(
        rf"(?m)^\w[\w \*]*\b{re.escape(name)}\s*\([^;]*?\)\s*\{{(.*?)^\}}",
        source,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match is not None, f"missing helper {name}"
    return match.group(1)


assert "bool translator_io_start(DisasContextBase *db);" in interface
assert "If icount is enabled" in interface

checked = 0
for suffix in ("tbl", "tbu", "atbl", "atbu"):
    for direction, call in (("read", "load"), ("write", "store")):
        wrapper = body(translator, f"spr_{direction}_{suffix}")
        boundary = "translator_io_start(&ctx->base);"
        helper = f"gen_helper_{call}_{suffix}("
        assert wrapper.count(boundary) == 1, f"missing or duplicate IO boundary: {direction}_{suffix}"
        assert wrapper.count(helper) == 1, f"missing or duplicate helper: {direction}_{suffix}"
        assert wrapper.index(boundary) < wrapper.index(helper), f"late IO boundary: {direction}_{suffix}"
        name = f"cpu_ppc_{call}_{suffix}"
        clock = body(timebase, name)
        # The high-half TBU helpers delegate to their private implementations.
        if "qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)" not in clock:
            delegated = f"_cpu_ppc_{call}_{suffix}"
            assert delegated + "(env" in clock, f"unexpected clock delegation in {name}"
            clock = body(timebase, delegated)
        assert "qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)" in clock, (
            f"clock contract changed for {call}_{suffix}; review TCG IO policy"
        )
        checked += 1

assert checked == 8
print("PowerPC TCG timebase io-start contracts: 8 of 8 guarded")
