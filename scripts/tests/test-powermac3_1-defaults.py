#!/usr/bin/env python3
"""Guard the launch-era PowerMac3,1 retail machine defaults."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
POWER_MAC = ROOT / "hw/ppc/powermac3_1.c"
MAC_NEWWORLD = ROOT / "hw/ppc/mac_newworld.c"
OHCI_PCI = ROOT / "hw/usb/hcd-ohci-pci.c"
PCI_HEADER = ROOT / "include/hw/pci/pci.h"
PPC_KCONFIG = ROOT / "hw/ppc/Kconfig"

power_mac = POWER_MAC.read_text(encoding="utf-8")
mac_newworld = MAC_NEWWORLD.read_text(encoding="utf-8")
ohci_pci = OHCI_PCI.read_text(encoding="utf-8")
pci_header = PCI_HEADER.read_text(encoding="utf-8")
kconfig = PPC_KCONFIG.read_text(encoding="utf-8")
errors: list[str] = []

# Keep the profile coherent with the original 450 MHz / 128 MiB retail
# Sawtooth configuration instead of inheriting generic mac99's 900 MHz
# firmware value.
required_profile = (
    '#define POWERMAC3_1_DEFAULT_CLOCK_FREQUENCY (450UL * 1000UL * 1000UL)',
    '#define POWERMAC3_1_DEFAULT_BUS_FREQUENCY (100UL * 1000UL * 1000UL)',
    'POWERPC_CPU_TYPE_NAME("7400_v2.9")',
    'mc->default_ram_size = 128 * MiB;',
    'object_property_set_str(obj, "via", "pmu", &error_abort);',
    'fw_cfg_modify_i32(fw_cfg, FW_CFG_PPC_CLOCKFREQ,',
    'POWERMAC3_1_DEFAULT_CLOCK_FREQUENCY);',
    'fw_cfg_modify_i32(fw_cfg, FW_CFG_PPC_BUSFREQ,',
    'POWERMAC3_1_DEFAULT_BUS_FREQUENCY);',
)
for needle in required_profile:
    if needle not in power_mac:
        errors.append(f"PowerMac3,1 retail default missing: {needle}")

parent_init = power_mac.find("powermac3_1_parent_init(machine);")
clock_override = power_mac.find("fw_cfg_modify_i32(fw_cfg, FW_CFG_PPC_CLOCKFREQ")
agp_resolve = power_mac.find("TYPE_UNI_NORTH_AGP_HOST_BRIDGE")
if not (0 <= parent_init < clock_override < agp_resolve):
    errors.append("Sawtooth firmware frequency override must follow mac99 init and precede AGP display setup")

# The generic compatibility machine must retain its own known-good frequency;
# this historical correction belongs to powermac3_1 only.
if '#define CLOCKFREQ (900UL * 1000UL * 1000UL)' not in mac_newworld:
    errors.append("generic mac99 clock-frequency default changed unexpectedly")
if 'fw_cfg_add_i32(fw_cfg, FW_CFG_PPC_CLOCKFREQ, CLOCKFREQ);' not in mac_newworld:
    errors.append("generic mac99 no longer publishes its own clock-frequency")

# The factory display substitute is QEMU's Rage128-family model with the same
# 16 MiB VRAM size as the launch card, installed at Sawtooth's AGP slot 0x10.
required_video = (
    'pci_new(PCI_DEVFN(16, 0), "ati-vga")',
    'qdev_prop_set_string(DEVICE(dev), "model", "rage128p")',
    'qdev_prop_set_uint32(DEVICE(dev), "vgamem_mb", 16)',
    'case VGA_STD:',
    'return powermac3_1_rage128_init(bus);',
)
for needle in required_video:
    if needle not in power_mac:
        errors.append(f"PowerMac3,1 Rage 128 default missing: {needle}")

# A real PowerMac3,1 enumerates both KeyLargo OHCI functions as Apple 106b:0019.
# Keep pci-ohci's existing 106b:003f identity as its compatibility default, but
# make the historical Sawtooth profile override only its two built-in devices.
if '#define PCI_DEVICE_ID_APPLE_KEYLARGO_USB 0x0019' not in pci_header:
    errors.append("Apple KeyLargo USB PCI device ID 0x0019 is not named")
if 'DEFINE_PROP_UINT16("device-id", OHCIPCIState, device_id,' not in ohci_pci:
    errors.append("pci-ohci does not expose a per-device PCI identity override")
if 'PCI_DEVICE_ID_APPLE_IPID_USB)' not in ohci_pci:
    errors.append("pci-ohci compatibility default must remain Apple 0x003f")
if 'pci_set_word(dev->config + PCI_DEVICE_ID, ohci->device_id);' not in ohci_pci:
    errors.append("pci-ohci device-id property is not applied to PCI config space")
required_usb = (
    'pci_new(PCI_DEVFN(8, 0), "pci-ohci")',
    'pci_new(PCI_DEVFN(9, 0), "pci-ohci")',
    'qdev_prop_set_uint16(DEVICE(ohci), "device-id",',
    'PCI_DEVICE_ID_APPLE_KEYLARGO_USB);',
)
for needle in required_usb:
    if needle not in mac_newworld:
        errors.append(f"PowerMac3,1 KeyLargo USB identity missing: {needle}")

# Since the machine creates ati-vga as a default device, the NewWorld build
# must guarantee that model is present rather than merely hoping Kconfig chose it.
newworld_start = kconfig.find("config MAC_NEWWORLD")
newworld_end = kconfig.find("\nconfig ", newworld_start + 1)
newworld = kconfig[newworld_start:newworld_end if newworld_end >= 0 else None]
if "select ATI_VGA" not in newworld:
    errors.append("MAC_NEWWORLD must select ATI_VGA for the Sawtooth factory display")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 retail defaults: verified")
