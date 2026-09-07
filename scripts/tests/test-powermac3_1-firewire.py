#!/usr/bin/env python3
"""Guard the PowerMac3,1 TSB12LV23 FireWire controller contract."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TSB = ROOT / "hw/misc/tsb12lv23.c"
MISC_MESON = ROOT / "hw/misc/meson.build"
MISC_KCONFIG = ROOT / "hw/misc/Kconfig"
PPC_KCONFIG = ROOT / "hw/ppc/Kconfig"
POWER_MAC = ROOT / "hw/ppc/powermac3_1.c"

errors: list[str] = []

if not TSB.exists():
    errors.append("missing TSB12LV23 controller model: hw/misc/tsb12lv23.c")
    tsb = ""
else:
    tsb = TSB.read_text(encoding="utf-8")

meson = MISC_MESON.read_text(encoding="utf-8")
misc_kconfig = MISC_KCONFIG.read_text(encoding="utf-8")
ppc_kconfig = PPC_KCONFIG.read_text(encoding="utf-8")
power_mac = POWER_MAC.read_text(encoding="utf-8")

# Physical Sawtooth enumeration and the TI programming manual agree on the
# controller's PCI identity, INTA routing and OHCI programming interface.
required_identity = (
    '#define TYPE_TSB12LV23 "tsb12lv23"',
    'k->vendor_id = PCI_VENDOR_ID_TI;',
    'k->device_id = 0x8019;',
    'k->revision = 0x00;',
    'k->class_id = PCI_CLASS_SERIAL_FIREWIRE;',
    'pdev->config[PCI_CLASS_PROG] = 0x10;',
    'pci_config_set_interrupt_pin(pdev->config, 1);',
    'pdev->config[PCI_MIN_GNT] = 0x02;',
    'pdev->config[PCI_MAX_LAT] = 0x04;',
)
for needle in required_identity:
    if needle not in tsb:
        errors.append(f"TSB12LV23 PCI identity contract missing: {needle}")

# Real hardware exposes a 2 KiB OHCI window and a 16 KiB TI extension
# aperture.  Both are non-prefetchable 32-bit memory BARs.
required_bars = (
    '#define TSB12LV23_OHCI_SIZE 0x800',
    '#define TSB12LV23_TI_SIZE 0x4000',
    'memory_region_init_io(&s->ohci_mmio, OBJECT(s), &tsb12lv23_ohci_ops,',
    'memory_region_init_io(&s->ti_mmio, OBJECT(s), &tsb12lv23_ti_ops,',
    'pci_register_bar(pdev, 0, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ohci_mmio);',
    'pci_register_bar(pdev, 1, PCI_BASE_ADDRESS_SPACE_MEMORY, &s->ti_mmio);',
)
for needle in required_bars:
    if needle not in tsb:
        errors.append(f"TSB12LV23 BAR contract missing: {needle}")

# The controller must expose enough OHCI state for a guest driver to identify
# and reset it safely even before a separate IEEE-1394 PHY/bus is implemented.
required_ohci = (
    '#define OHCI_VERSION 0x000',
    '#define OHCI_BUS_ID 0x01c',
    '#define OHCI_HC_CONTROL_SET 0x050',
    '#define OHCI_HC_CONTROL_CLEAR 0x054',
    '#define OHCI_INT_EVENT_SET 0x080',
    '#define OHCI_INT_EVENT_CLEAR 0x084',
    '#define OHCI_INT_MASK_SET 0x088',
    '#define OHCI_INT_MASK_CLEAR 0x08c',
    '#define OHCI_PHY_CONTROL 0x0ec',
    'return 0x00010000;',
    'return 0x31333934;',
    'return UINT32_MAX;',
    'OHCI_HC_CONTROL_SOFT_RESET',
    'tsb12lv23_update_irq(s);',
)
for needle in required_ohci:
    if needle not in tsb:
        errors.append(f"TSB12LV23 OHCI probe/reset contract missing: {needle}")

# The real chip advertises PCI PM capability at 0x44; the observed Sawtooth-
# generation controller reports PM capability word 0x6411.
required_pm = (
    '#define TSB12LV23_PM_CAP_OFFSET 0x44',
    'pci_pm_init(pdev, TSB12LV23_PM_CAP_OFFSET, errp)',
    'pci_set_word(pdev->config + TSB12LV23_PM_CAP_OFFSET + PCI_PM_PMC, 0x6411);',
)
for needle in required_pm:
    if needle not in tsb:
        errors.append(f"TSB12LV23 power-management contract missing: {needle}")

# Migration must carry the PCI parent state as well as OHCI registers and must
# re-evaluate the level-triggered INTA line after a load.
required_migration = (
    'VMSTATE_PCI_DEVICE(parent_obj, TSB12LV23State),',
    'static int tsb12lv23_post_load(void *opaque, int version_id)',
    '.post_load = tsb12lv23_post_load,',
)
for needle in required_migration:
    if needle not in tsb:
        errors.append(f"TSB12LV23 migration contract missing: {needle}")

# Build with the NewWorld family, but instantiate only in the historical
# powermac3_1 wrapper after its parent has created the DEC 21154 bridge.
if "config TSB12LV23" not in misc_kconfig or "depends on PCI" not in misc_kconfig:
    errors.append("TSB12LV23 Kconfig symbol missing or not PCI-scoped")
if "CONFIG_TSB12LV23" not in meson or "tsb12lv23.c" not in meson:
    errors.append("TSB12LV23 source is not wired into hw/misc/meson.build")

newworld_start = ppc_kconfig.find("config MAC_NEWWORLD")
newworld_end = ppc_kconfig.find("\nconfig ", newworld_start + 1)
newworld = ppc_kconfig[newworld_start:newworld_end if newworld_end >= 0 else None]
if "select TSB12LV23" not in newworld:
    errors.append("MAC_NEWWORLD must select TSB12LV23 for the Sawtooth profile")

required_machine_wiring = (
    '#include "hw/pci-bridge/dec.h"',
    '#include "hw/pci/pci_bridge.h"',
    'TYPE_DEC_21154_P2P_BRIDGE',
    'south_pci_bus = pci_bridge_get_sec_bus(PCI_BRIDGE(south_bridge));',
    'pci_create_simple(south_pci_bus, PCI_DEVFN(0x0a, 0), "tsb12lv23");',
)
for needle in required_machine_wiring:
    if needle not in power_mac:
        errors.append(f"PowerMac3,1 FireWire wiring missing: {needle}")

parent_init = power_mac.find("powermac3_1_parent_init(machine);")
bridge_resolve = power_mac.find("TYPE_DEC_21154_P2P_BRIDGE")
firewire_create = power_mac.find(
    'pci_create_simple(south_pci_bus, PCI_DEVFN(0x0a, 0), "tsb12lv23");'
)
if not (0 <= parent_init < bridge_resolve < firewire_create):
    errors.append("TSB12LV23 must attach after parent Sawtooth bridge creation")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 TSB12LV23 FireWire controller: verified")
