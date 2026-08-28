#!/usr/bin/env python3
"""Guard generic PowerMac3,1 AGP + PCI multi-display wiring."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
POWER_MAC = ROOT / "hw/ppc/powermac3_1.c"

source = POWER_MAC.read_text(encoding="utf-8")
errors: list[str] = []

required = (
    '"agp-display"',
    'object_property_add_str',
    'TYPE_PCI_DEVICE',
    'DEVICE_CATEGORY_DISPLAY',
    'PCI_DEVFN(16, 0)',
)
for needle in required:
    if needle not in source:
        errors.append(f"PowerMac3,1 AGP display contract missing: {needle}")

# The AGP selector must preserve real device identities.  Do not solve
# multi-monitor by silently replacing user-selected cards with secondary-vga.
if '"secondary-vga"' in source:
    errors.append("PowerMac3,1 must not force secondary-vga for extra displays")

# Existing -vga behavior must remain as the fallback when no explicit AGP
# device model is selected.
if "powermac3_1_vga_init(agp_bus, requested_vga)" not in source:
    errors.append("PowerMac3,1 lost its existing -vga AGP fallback")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 generic AGP + PCI multi-display contract: verified")
