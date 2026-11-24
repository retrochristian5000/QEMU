#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reference model for the old BAT range used during replacement."""

PAGE = 0x1000
MASK32 = 0xffffffff


def pages(batu):
    if not batu & 3:
        return set()
    mask = (batu << 15) & 0x0ffe0000
    base = batu & ~0x1ffff & ~mask
    size = mask + 0x20000
    return {(base + offset) & MASK32 for offset in range(0, size, PAGE)}


# Shrink a valid 1 MiB mapping to 128 KiB at the same effective base.
old = 0xfff00000 | (7 << 2) | 2
new = 0xfff00000 | 2
assert len(pages(old)) == 256
assert len(pages(new)) == 32
for ea in (0xfffc4d50, 0xfffc5d60, 0xfffcebfc):
    assert ea & ~0xfff in pages(old) - pages(new)
assert not pages(old & ~3)
# Last block in the 32-bit address space must not wrap the page set.
assert max(pages(old)) == 0xfffff000
print("PPC32 BAT replacement range model passed")
