#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
core = (ROOT / "hw/pci/pci.c").read_text(encoding="utf-8")
bridge = (ROOT / "hw/pci/pci_bridge.c").read_text(encoding="utf-8")
bus = (ROOT / "include/hw/pci/pci_bus.h").read_text(encoding="utf-8")

assert "bool map_irq_default_swizzle;" in bus
assert "map_irq == pci_swizzle_map_irq_fn" in core
assert "sec_bus->map_irq == pci_swizzle_map_irq_fn" in bridge

start = core.index("static void pci_bus_change_irq_level")
end = core.index("\n}\n", start) + 3
change = core[start:end]
assert "old_level = bus->irq_count[irq_num] != 0;" in change
assert "new_level = bus->irq_count[irq_num] != 0;" in change
assert "if (old_level != new_level)" in change
assert "bus->set_irq(bus->irq_opaque, irq_num, new_level);" in change

start = core.index("static inline int pci_map_irq")
end = core.index("\n}\n", start) + 3
mapper = core[start:end]
assert "likely(bus->map_irq_default_swizzle)" in mapper
assert "return pci_swizzle_map_irq_fn(pci_dev, irq_num);" in mapper
assert "return bus->map_irq(pci_dev, irq_num);" in mapper

start = core.index("static void pci_change_irq_level")
end = core.index("\n}\n", start) + 3
route = core[start:end]
assert "irq_num = pci_map_irq(bus, pci_dev, irq_num);" in route
assert "bus->map_irq(pci_dev, irq_num)" not in route

print("ARM64e PCI INTx hot-path audit passed")
