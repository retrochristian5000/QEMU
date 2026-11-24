#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard the UniNorth PCI enumeration contract in the OpenBIOS submodule."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PCI = (ROOT / "roms/openbios/drivers/pci.c").read_text(encoding="utf-8")
MACIO = (ROOT / "roms/openbios/drivers/macio.c").read_text(encoding="utf-8")


def require(source: str, needle: str, label: str) -> None:
    if needle not in source:
        raise SystemExit(f"Missing {label}: {needle}")


require(PCI, "if (!(is_host_bridge && ob_pci_is_uninorth_root())) {",
        "root BAR-probe exclusion")
require(PCI, "ob_scan_pci_bus(bus_num, mem_base, io_base, config.path, bus);",
        "direct root scan")
require(PCI, "config.subordinate_bus = *bus_num;",
        "discovered subordinate bus range")
require(PCI, "io_base = 0x1000;", "reserved UniNorth low I/O ports")
require(MACIO, "arch = saved_arch;", "primary root restoration")
require(MACIO, "Warning: unable to enumerate PCI root %s",
        "root enumeration diagnostic")

bridge = PCI.split("static void ob_configure_pci_bridge(", 1)[1]
bridge = bridge.split("static int ob_pci_read_identification", 1)[0]
window = bridge.index("((arch->pci_mem_base + arch->mem_len - 1) >> 16)")
scan = bridge.index("/* make pci bridge parent device, prepare for recursion */")
final = bridge.index("/* Set the limit registers */")
if not window < scan < final:
    raise SystemExit("DEC memory forwarding must precede the child scan")

print("PowerMac3,1 PCI enumeration source contract: verified")
