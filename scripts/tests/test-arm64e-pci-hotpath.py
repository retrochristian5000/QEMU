#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
host = (ROOT / "hw/pci/pci_host.c").read_text(encoding="utf-8")
core = (ROOT / "hw/pci/pci.c").read_text(encoding="utf-8")
device = (ROOT / "include/hw/pci/pci_device.h").read_text(encoding="utf-8")

for token in (
    "bool config_read_default;",
    "bool config_write_default;",
):
    assert token in device, f"missing PCI callback fast-path state: {token}"

for token in (
    "config_read == pci_default_read_config",
    "config_write == pci_default_write_config",
):
    assert token in core, f"missing PCI callback classification: {token}"

for token in (
    "if (likely(pci_dev->config_read_default))",
    "ret = pci_default_read_config(pci_dev, addr, len);",
    "if (likely(pci_dev->config_write_default))",
    "pci_default_write_config(pci_dev, addr, val, len);",
):
    assert token in host, f"missing PCI direct default-handler path: {token}"

late_overrides = {
    "hw/net/e1000.c": (
        "pci_dev->config_write = e1000_write_config;",
        "pci_dev->config_write_default = false;",
    ),
    "hw/net/e1000e.c": (
        "pci_dev->config_write = e1000e_write_config;",
        "pci_dev->config_write_default = false;",
    ),
    "hw/net/igb.c": (
        "pci_dev->config_write = igb_write_config;",
        "pci_dev->config_write_default = false;",
    ),
    "hw/net/igbvf.c": (
        "dev->config_write = igbvf_write_config;",
        "dev->config_write_default = false;",
    ),
}

for relpath, tokens in late_overrides.items():
    text = (ROOT / relpath).read_text(encoding="utf-8")
    first = text.index(tokens[0])
    second = text.index(tokens[1], first)
    assert second > first, f"stale PCI callback fast-path state in {relpath}"

print("ARM64e PCI config hot-path audit passed")
