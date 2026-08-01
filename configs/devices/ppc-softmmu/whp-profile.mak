# WHP basic Classic Mac OS profile for qemu-system-ppc.
#
# Keep the build focused on QEMU's supported PowerMac boards:
#   - g3beige (OldWorld / Heathrow)
#   - mac99   (NewWorld / UniNorth)
#
# Core board dependencies such as ADB, MacIO, IDE, NVRAM, PCI host bridges,
# interrupt controllers, and fw_cfg are selected by the board symbols below.

# Do not pull in every generic PCI or test device.
CONFIG_PCI_DEVICES=n
CONFIG_TEST_DEVICES=n

# PowerMac boards used for Classic Mac OS 8 and 9 experiments.
CONFIG_MAC_OLDWORLD=y
CONFIG_MAC_NEWWORLD=y

# QEMU's standard PCI VGA, used with the bundled qemu_vga.ndrv path.
CONFIG_VGA_PCI=y

# Board-default network adapters.
CONFIG_NE2000_PCI=y
CONFIG_SUNGEM=y

# Basic NewWorld USB support while retaining ADB input on both boards.
CONFIG_USB_OHCI_PCI=y
CONFIG_USB_HUB=y
CONFIG_USB_HID=y
