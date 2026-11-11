#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
pic = (ROOT / "hw/intc/i8259.c").read_text(encoding="utf-8")

required = (
    '#include "qemu/bitops.h"',
    '#include "qemu/host-utils.h"',
    "rotated = ror8(mask, s->priority_add);",
    "return ctz32(rotated);",
)

for token in required:
    assert token in pic, f"missing i8259 ARM64 hot-path contract: {token}"

start = pic.index("static int get_priority(PICCommonState *s, int mask)")
end = pic.index("\n}\n", start) + 3
priority = pic[start:end]

assert "while (" not in priority, (
    "i8259 priority lookup regressed to a data-dependent probe loop"
)
assert "priority++" not in priority, (
    "i8259 priority lookup regressed to iterative bit probing"
)

print("ARM64e i8259 PIC hot-path audit passed")
