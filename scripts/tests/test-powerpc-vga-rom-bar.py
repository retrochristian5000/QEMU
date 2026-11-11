#!/usr/bin/env python3
"""Guard the PowerPC/OpenBIOS standard-VGA option-ROM contract.

Mac99 still uses OpenBIOS's built-in VGA FCode for device setup, but the
standard PCI VGA device must retain its normal QEMU option ROM.  The PCI core
uses that ROM to create PCI expansion-ROM BAR 6 and replace the UINT32_MAX
romsize sentinel with the actual, power-of-two ROM size.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
VGA_PCI = ROOT / "hw/display/vga-pci.c"
PCI_CORE = ROOT / "hw/pci/pci.c"

vga = VGA_PCI.read_text(encoding="utf-8")
pci = PCI_CORE.read_text(encoding="utf-8")

errors: list[str] = []

# The August 2026 Mac99 special-case set romfile to the empty string during
# device realize.  pci_qdev_realize() interprets a non-NULL romfile as an
# explicit choice, so it then skips the class default vgabios-stdvga.bin.
# pci_add_option_rom() sees the empty string and returns before BAR 6 exists.
if "pci_vga_uses_open_firmware" in vga:
    errors.append("standard VGA still has the Mac99 ROM-suppression helper")
if 'dev->romfile = g_strdup("")' in vga:
    errors.append("standard VGA still suppresses the option ROM on Mac99")

if 'k->romfile = "vgabios-stdvga.bin";' not in vga:
    errors.append("standard VGA lost its default vgabios-stdvga.bin")

# Keep the generic PCI semantics that turn the class ROM into expansion-ROM
# BAR 6 and resolve the UINT32_MAX property sentinel to a real size.
required_pci_contract = (
    'DEFINE_PROP_UINT32("romsize", PCIDevice, romsize, UINT32_MAX)',
    "if (!pdev->romfile || !strlen(pdev->romfile))",
    "pdev->romsize = pow2ceil(size);",
    "pci_register_bar(pdev, PCI_ROM_SLOT, 0, &pdev->rom);",
)
for needle in required_pci_contract:
    if needle not in pci:
        errors.append(f"PCI option-ROM contract changed or disappeared: {needle}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerPC VGA option-ROM/BAR6 contract: verified")
