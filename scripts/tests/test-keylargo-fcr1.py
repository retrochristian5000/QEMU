#!/usr/bin/env python3
"""Guard the original KeyLargo FCR1 register contract used by Sawtooth."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
MACIO = ROOT / "hw/misc/macio/macio.c"

text = MACIO.read_text(encoding="utf-8")
errors: list[str] = []

# AppleKeyLargo's original KeyLargo FCR1 layout.  Keep these separate from
# later Pangea/Intrepid/K2 meanings so the PowerMac3,1 machine cannot silently
# inherit a newer southbridge ABI.
required_bits = {
    "KL_FCR1_AUDIO_SEL22M_CLK": 1,
    "KL_FCR1_AUDIO_CLK_ENABLE": 3,
    "KL_FCR1_AUDIO_CLK_OUT_ENABLE": 5,
    "KL_FCR1_AUDIO_CELL_ENABLE": 6,
    "KL_FCR1_CHOOSE_AUDIO": 7,
    "KL_FCR1_CHOOSE_I2S0": 9,
    "KL_FCR1_I2S0_CELL_ENABLE": 10,
    "KL_FCR1_I2S0_CLK_ENABLE": 12,
    "KL_FCR1_I2S0_ENABLE": 13,
    "KL_FCR1_I2S1_CELL_ENABLE": 17,
    "KL_FCR1_I2S1_CLK_ENABLE": 19,
    "KL_FCR1_I2S1_ENABLE": 20,
    "KL_FCR1_EIDE0_ENABLE": 23,
    "KL_FCR1_EIDE0_RESET_N": 24,
    "KL_FCR1_EIDE1_ENABLE": 26,
    "KL_FCR1_EIDE1_RESET_N": 27,
    "KL_FCR1_UIDE_ENABLE": 29,
    "KL_FCR1_UIDE_RESET_N": 30,
}

lines = text.splitlines()
for name, bit in required_bits.items():
    prefix = f"#define {name}"
    line = next((line for line in lines if line.startswith(prefix)), "")
    if f"(1U << {bit})" not in line:
        errors.append(f"missing or incorrect KeyLargo FCR1 bit {name} at {bit}")

if "#define KL_FCR1_VALID_MASK" not in text:
    errors.append("KeyLargo FCR1 needs an explicit valid-bit mask")

# Reserved FCR1 positions must not become sticky guest-visible state.  This is
# deliberately a register-level rule; actual audio/I2S/ATA clock side effects
# can be attached independently as those devices are modeled.
if "if (reg == 1)" not in text or "value &= KL_FCR1_VALID_MASK;" not in text:
    errors.append("KeyLargo FCR1 writes must discard reserved bits")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("KeyLargo FCR1 register contract: verified")
