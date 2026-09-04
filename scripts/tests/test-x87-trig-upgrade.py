#!/usr/bin/env python3
"""Regression guard for the WHP x87 transcendental upgrade."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def main() -> None:
    trig_path = ROOT / "target/i386/tcg/fpu_trig_helper.c"
    assert trig_path.is_file(), "missing x87 floatx80 trig helper"

    trig = trig_path.read_text(encoding="utf-8")
    helper_defs = read("target/i386/helper.h")
    helper_tcg = read("target/i386/tcg/helper-tcg.h")
    meson = read("target/i386/tcg/meson.build")

    for op in ("fsin", "fcos", "fptan"):
        assert f"DEF_HELPER_1({op}_whp, void, env)" in helper_defs
        assert f"#define gen_helper_{op} gen_helper_{op}_whp" in helper_tcg
        assert f"helper_{op}_whp" in trig

    for donor in ("floatx80_sin", "floatx80_cos", "floatx80_tan"):
        assert donor in trig, f"missing {donor} donor path"

    assert "fpu_trig_helper.c" in meson
    assert "../../m68k/softfloat.c" in meson

    # The upgraded path must never collapse x87 inputs to host double/libm.
    assert "floatx80_to_float64" not in trig
    assert "floatx80_to_double" not in trig
    assert "double_to_floatx80" not in trig
    assert not re.search(r"(?<!floatx80_)\b(?:sin|cos|tan)\s*\(", trig)

    # Preserve the x87 range/C2 contract instead of delegating it to FPSP.
    assert "X87_TRIG_MAX_EXP" in trig
    assert "X87_FPU_C2" in trig
    assert "x87_trig_out_of_range" in trig


if __name__ == "__main__":
    main()
