#!/usr/bin/env python3
"""Guard the QEMU -> SeaBIOS -g display-mode ABI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OPTIONS = (ROOT / "qemu-options.hx").read_text(encoding="utf-8")
FWCFG = (ROOT / "hw/i386/fw_cfg.c").read_text(encoding="utf-8")

option = OPTIONS.index('DEF("g", HAS_ARG, QEMU_OPTION_g')
option_block = OPTIONS[option:option + 500]
assert "QEMU_ARCH_I386" in option_block, "-g must be available to x86 system emulators"

required_fwcfg = (
    '"etc/qemu-display-width"',
    '"etc/qemu-display-height"',
    '"etc/qemu-display-depth"',
    "cpu_to_le32(graphic_width)",
    "cpu_to_le32(graphic_height)",
    "cpu_to_le32(graphic_depth)",
)
for token in required_fwcfg:
    assert token in FWCFG, f"missing SeaBIOS -g producer contract: {token}"

assert (
    "graphic_width > 0 && graphic_height > 0" in FWCFG
    or "graphic_width <= 0 || graphic_height <= 0" in FWCFG
), "x86 fw_cfg display-mode geometry guard missing"

print("QEMU -> SeaBIOS -g display-mode ABI: verified")
