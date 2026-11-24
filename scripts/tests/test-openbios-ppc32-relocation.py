#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Model PPC32 OpenBIOS startup hash mappings; this is not a boot test."""

from collections import defaultdict

PROM = 0xfff00000
SIZE = 0x100000
PAGE = 0x1000
HASH = 0x10000


def entry(ea, pa):
    vsid = (ea >> 28) + 0x400
    group = (vsid ^ ((ea >> 12) & 0xffff)) & 0x3ff
    tag = 0x80000000 | (vsid << 7) | ((ea & 0x0fffffff) >> 22)
    return group, tag, pa | 2


def check(ram):
    rom_copy = ram - SIZE
    hash_base = (rom_copy - HASH) & ~0xfffff
    groups = defaultdict(dict)
    mappings = [(PROM + offset, rom_copy + offset)
                for offset in range(0, SIZE, PAGE)]
    mappings += [(addr, addr)
                 for addr in range(hash_base - 96 * 1024, hash_base, PAGE)]
    for ea, pa in mappings:
        group, tag, value = entry(ea, pa)
        assert tag not in groups[group], (hex(ea), group, tag)
        groups[group][tag] = value
        assert len(groups[group]) <= 8, group
    for offset in (0, 0xc4d50, 0xcebfc, SIZE - 1):
        ea = PROM + offset
        group, tag, _ = entry(ea, 0)
        pa = (groups[group][tag] & ~0xfff) | (ea & 0xfff)
        assert pa == rom_copy + offset
        assert pa < ram


for mib in (32, 64, 128, 256, 512, 1024, 2048):
    check(mib * 1024 * 1024)

print("PPC32 startup mapping model: all firmware pages and stack pages fit")
