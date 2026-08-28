#!/usr/bin/env python3
"""Guard generic PowerMac3,1 AGP + PCI multi-display wiring."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
POWER_MAC = ROOT / "hw/ppc/powermac3_1.c"
MAC_NEWWORLD = ROOT / "hw/ppc/mac_newworld.c"

power_mac = POWER_MAC.read_text(encoding="utf-8")
mac_newworld = MAC_NEWWORLD.read_text(encoding="utf-8")
errors: list[str] = []

# Keep the inherited creation order that makes the AGP root pci.0 and the main
# PCI-slot root the default destination for an extra `-device`.
agp_pos = mac_newworld.find("TYPE_UNI_NORTH_AGP_HOST_BRIDGE")
internal_pos = mac_newworld.find("TYPE_UNI_NORTH_INTERNAL_PCI_HOST_BRIDGE")
main_pos = mac_newworld.find("TYPE_UNI_NORTH_PCI_HOST_BRIDGE")
if not (0 <= agp_pos < internal_pos < main_pos):
    errors.append("UniNorth AGP/internal/main root creation order changed")
if "this must be last to make it the default" not in mac_newworld:
    errors.append("main UniNorth PCI default-bus invariant lost")

# PowerMac3,1 publishes pci.0 as its AGP slot contract and verifies that the
# inherited topology still gives that name to the resolved AGP bus.  This lets
# users place any real PCI display model in AGP with bus=pci.0 while an extra
# unqualified -device remains on the normal PCI-slot root.
required = (
    '#define POWERMAC3_1_AGP_BUS_NAME "pci.0"',
    "TYPE_UNI_NORTH_AGP_HOST_BRIDGE",
    "qbus_get_name(BUS(agp_bus))",
    "POWERMac3,1 AGP bus expected",
    "PCI_DEVFN(16, 0)",
    "powermac3_1_vga_init(agp_bus, requested_vga)",
)
for needle in required:
    if needle not in power_mac:
        errors.append(f"PowerMac3,1 AGP display contract missing: {needle}")

# Never flatten extra real cards into the QEMU-specific secondary-vga model.
if '"secondary-vga"' in power_mac:
    errors.append("PowerMac3,1 must not force secondary-vga for extra displays")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 generic AGP + PCI multi-display contract: verified")
