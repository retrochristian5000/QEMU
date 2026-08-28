#!/usr/bin/env python3
"""Guard generic PowerMac3,1 AGP + PCI multi-display wiring."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
POWER_MAC = ROOT / "hw/ppc/powermac3_1.c"
MAC_NEWWORLD = ROOT / "hw/ppc/mac_newworld.c"
UNINORTH = ROOT / "hw/pci-host/uninorth.c"

power_mac = POWER_MAC.read_text(encoding="utf-8")
mac_newworld = MAC_NEWWORLD.read_text(encoding="utf-8")
uninorth = UNINORTH.read_text(encoding="utf-8")
errors: list[str] = []


def function_body(source: str, name: str, next_name: str) -> str:
    start = source.find(f"static void {name}")
    end = source.find(f"static void {next_name}", start + 1)
    if start < 0 or end < 0:
        return ""
    return source[start:end]


# Sawtooth exposes three independent UniNorth PCI roots.  Their bus names are
# part of the user-facing multi-display contract: pci.0 is AGP, pci.1 is the
# internal root, and pci.2 is the normal PCI-slot root/default bus.
root_contracts = (
    ("pci_unin_agp_realize", "pci_unin_agp_init", 'pci_register_root_bus(dev, "pci.0"'),
    ("pci_unin_internal_realize", "pci_unin_internal_init", 'pci_register_root_bus(dev, "pci.1"'),
    ("pci_unin_main_realize", "pci_unin_main_init", 'pci_register_root_bus(dev, "pci.2"'),
)
for function, next_function, needle in root_contracts:
    body = function_body(uninorth, function, next_function)
    if needle not in body:
        errors.append(f"stable UniNorth bus contract missing in {function}: {needle}")

# Keep the creation order that makes the main PCI root the default destination
# for an extra `-device`, while the first explicitly addressed card can occupy
# the AGP root at pci.0.
agp_pos = mac_newworld.find("TYPE_UNI_NORTH_AGP_HOST_BRIDGE")
internal_pos = mac_newworld.find("TYPE_UNI_NORTH_INTERNAL_PCI_HOST_BRIDGE")
main_pos = mac_newworld.find("TYPE_UNI_NORTH_PCI_HOST_BRIDGE")
if not (0 <= agp_pos < internal_pos < main_pos):
    errors.append("UniNorth AGP/internal/main root creation order changed")
if "this must be last to make it the default" not in mac_newworld:
    errors.append("main UniNorth PCI default-bus invariant lost")

# PowerMac3,1's automatic display must still use the real AGP host, and the
# machine profile must never substitute a secondary-vga model for user cards.
for needle in ("TYPE_UNI_NORTH_AGP_HOST_BRIDGE", "PCI_DEVFN(16, 0)",
               "powermac3_1_vga_init(agp_bus, requested_vga)"):
    if needle not in power_mac:
        errors.append(f"PowerMac3,1 AGP display contract missing: {needle}")
if '"secondary-vga"' in power_mac:
    errors.append("PowerMac3,1 must not force secondary-vga for extra displays")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 generic AGP + PCI multi-display contract: verified")
