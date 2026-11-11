#!/usr/bin/env python3
"""Guard the PowerMac3,1 Rage128 DDC/MONID contract."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
ATI_C = ROOT / "hw/display/ati.c"
ATI_REGS = ROOT / "hw/display/ati_regs.h"

ati_c = ATI_C.read_text(encoding="utf-8")
ati_regs = ATI_REGS.read_text(encoding="utf-8")
errors: list[str] = []

# The single-head Rage128 VGA DDC path used by Sawtooth is carried on
# GPIO_MONID data line 1 and clock line 2.
for needle in (
    "#define GPIO_MONID_A_1                          BIT(1)",
    "#define GPIO_MONID_A_2                          BIT(2)",
    "#define GPIO_MONID_Y_1                          BIT(9)",
    "#define GPIO_MONID_Y_2                          BIT(10)",
    "#define GPIO_MONID_EN_1                         BIT(17)",
    "#define GPIO_MONID_EN_2                         BIT(18)",
    "#define GPIO_MONID_MASK_1                       BIT(25)",
    "#define GPIO_MONID_MASK_2                       BIT(26)",
):
    if needle not in ati_regs:
        errors.append(f"Rage128 MONID definition missing: {needle}")

# Updating one DDC pair must not wipe the two unrelated MONID sense inputs.
if "data &= ~0xf00ULL;" in ati_c:
    errors.append("DDC helper must not clear every MONID Y input")
if "data &= ~(BIT(base + 8) | BIT(base + 9));" not in ati_c:
    errors.append("DDC helper must update only its selected Y input pair")

# Rage128 DDC needs to see partial byte writes and line release, not merely a
# narrow enable-bit write pattern guarded by magic masks.
write_start = ati_c.find("static void ati_mm_write")
monid_start = ati_c.find("case GPIO_MONID ... GPIO_MONID + 3:", write_start)
monid_end = ati_c.find("case PALETTE_INDEX", monid_start)
if write_start < 0 or monid_start < 0 or monid_end < 0:
    errors.append("Rage128 GPIO_MONID write handler is missing")
else:
    monid = ati_c[monid_start:monid_end]
    if "ati_reg_write_offs(&s->regs.gpio_monid" not in monid:
        errors.append("Rage128 MONID partial writes are not preserved")
    if "ati_i2c(&s->bbi2c" not in monid or "s->regs.gpio_monid, 1" not in monid:
        errors.append("Rage128 VGA DDC must use MONID data 1 / clock 2")
    if "0x60000" in monid or "BIT(25)" in monid:
        errors.append("Rage128 MONID handler must not rely on anonymous magic masks")

# Released open-drain DDC lines should be sampled high before the first guest
# transaction, so firmware/driver read-before-write probes see an idle bus.
realize_start = ati_c.find("/* ddc, edid */")
realize_end = ati_c.find("/* mmio register space */", realize_start)
if realize_start < 0 or realize_end < 0:
    errors.append("ATI DDC realize block is missing")
else:
    realize = ati_c[realize_start:realize_end]
    if "s->regs.gpio_monid = ati_i2c(&s->bbi2c, s->regs.gpio_monid, 1);" not in realize:
        errors.append("Rage128 MONID inputs must be initialized to idle DDC levels")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 Rage128 DDC contract: verified")
