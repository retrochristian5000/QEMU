#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
piix = (ROOT / "hw/isa/piix.c").read_text(encoding="utf-8")
ich9 = (ROOT / "hw/isa/lpc_ich9.c").read_text(encoding="utf-8")

for token in (
    "static bool piix_get_irq_pic_level(PIIXState *s, int pic_irq)",
    "old_level = piix_get_irq_pic_level(s, pic_irq);",
    "new_level = piix_get_irq_pic_level(s, pic_irq);",
    "if (old_level != new_level)",
):
    assert token in piix, f"missing PIIX ISA hot-path contract: {token}"

start = piix.index("static void piix_set_pci_irq_level(PIIXState *s")
end = piix.index("\n}\n", start) + 3
piix_level = piix[start:end]
assert "qemu_set_irq(s->isa_irqs_in[pic_irq], new_level);" in piix_level
assert "piix_set_irq_pic(s, pic_irq);" not in piix_level

for token in (
    "static bool ich9_lpc_pic_has_pirq_source",
    "static bool ich9_lpc_pic_has_other_source",
    "if (!pic_dis &&",
    "!ich9_lpc_pic_has_other_source(lpc, pic_irq, pirq)",
    "if (apic_gsi != lpc->sci_gsi || !lpc->sci_level)",
):
    assert token in ich9, f"missing ICH9 ISA hot-path contract: {token}"

start = ich9.index("static void ich9_lpc_set_irq")
end = ich9.index("\n}\n", start) + 3
ich9_set = ich9[start:end]
assert "ich9_lpc_update_pic" not in ich9_set
assert "ich9_lpc_update_apic" not in ich9_set

start = ich9.index("static void ich9_set_sci")
end = ich9.index("\n}\n", start) + 3
sci = ich9[start:end]
assert "pci_bus_get_irq_level" in sci
assert "ich9_lpc_pic_has_pirq_source" in sci

print("ARM64e ISA IRQ hot-path audit passed")
