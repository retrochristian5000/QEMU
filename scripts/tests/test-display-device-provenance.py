#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check physical VGA retention and opt-in VMware SVGA Kconfig semantics."""
from __future__ import annotations

import pathlib
import re
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from minikconf import KconfigData, KconfigParser  # noqa: E402

config = (ROOT / "hw/display/Kconfig").read_text(encoding="utf-8")
meson = (ROOT / "hw/display/meson.build").read_text(encoding="utf-8")


def block(name: str) -> str:
    match = re.search(rf"(?ms)^config {re.escape(name)}\n.*?(?=^config |\Z)", config)
    assert match, f"missing device Kconfig symbol: {name}"
    return match.group(0)


vmware = block("VMWARE_VGA")
standard = block("VGA_PCI")
assert "default n" in vmware and "default y" not in vmware
assert "depends on PCI" in vmware and "select VGA" in vmware
assert "default y if PCI_DEVICES" in standard
assert (ROOT / "hw/display/vmware_vga.c").is_file()
assert (ROOT / "hw/display/vga-pci.c").is_file()
assert "'CONFIG_VMWARE_VGA'" in meson
assert "'CONFIG_VGA_PCI'" in meson
assert "1234:1111" in (ROOT / "docs/specs/standard-vga.rst").read_text(encoding="utf-8")


def evaluate(enable_vmware: bool) -> dict[str, bool]:
    # Exercise real minikconf semantics using extracted, unmodified stanzas.
    stub = ("config PCI\n    bool\n"
            "config PCI_DEVICES\n    bool\n"
            "config VGA\n    bool\n"
            "config EDID\n    bool\n")
    assignments = "CONFIG_PCI=y\nCONFIG_PCI_DEVICES=y\n"
    if enable_vmware:
        assignments += "CONFIG_VMWARE_VGA=y\n"
    with tempfile.TemporaryDirectory(prefix="whp-display-provenance-") as td:
        path = pathlib.Path(td) / "Kconfig"
        path.write_text(stub + standard + vmware + assignments,
                        encoding="utf-8")
        data = KconfigData()
        with path.open(encoding="utf-8") as stream:
            KconfigParser.parse(stream, data)
        return data.compute_config()


default = evaluate(False)
explicit = evaluate(True)
assert default["VGA_PCI"] and default["VGA"]
assert not default["VMWARE_VGA"], "virtual VMware adapter enabled by default"
assert explicit["VMWARE_VGA"], "VMware compatibility cannot be enabled"
assert explicit["VGA_PCI"] and explicit["VGA"]
print("VGA preserved; VMware SVGA excluded by default and explicitly available")
