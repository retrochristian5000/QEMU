#!/usr/bin/env python3
"""Structural guard for the incomplete Motorola MC6809 CPU skeleton."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
read = lambda p: (root / p).read_text(encoding="utf-8")
cpu = read("target/m6809/cpu.c")
h = read("target/m6809/cpu.h")
tcg = read("target/m6809/translate.c")
qom = read("target/m6809/cpu-qom.h")

assert "TARGET_ARCH=m6809" in read("configs/targets/m6809-softmmu.mak")
assert "TARGET_BIG_ENDIAN=y" in read("configs/targets/m6809-softmmu.mak")
assert "subdir('m6809')" in read("target/meson.build")
assert "source m6809/Kconfig" in read("target/Kconfig")
assert "M6809_RESET_VECTOR 0xfffeu" in h
assert "M6809_CC_I 0x10" in h
assert "M6809_CC_F 0x40" in h
assert "TYPE_M6809_6809_CPU" in qom
assert "TYPE_M6809_6809E_CPU" in qom
assert "env->dp = 0;" in cpu
assert "env->cc |= M6809_CC_I | M6809_CC_F;" in cpu
assert "address_space_lduw_be" in cpu
assert "#define CPU_INTERRUPT_NMI CPU_INTERRUPT_TGT_EXT_0" in h
assert "#define CPU_INTERRUPT_FIR CPU_INTERRUPT_TGT_EXT_1" in h
assert "'m6809'" in read("qapi/machine.json")
assert "case 0x12:" in tcg and "translator_ldub" in tcg
assert "LOG_UNIMP" in tcg and "DISAS_NORETURN" in tcg
assert "target_arch += {'m6809': m6809_ss}" in read("target/m6809/meson.build")
print("MC6809 minimal CPU skeleton wiring: verified")
