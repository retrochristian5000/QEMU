#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sawtooth KeyLargo DB-DMA register and physical address source contract.

A real QTest uses the Sawtooth PCI bridge and Screamer channel 0x10 to check
CMDPTR locking, STATUS read-only behavior and an address-zero descriptor.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
dma = (ROOT / "hw/misc/macio/mac_dbdma.c").read_text(encoding="utf-8")
header = (ROOT / "include/hw/ppc/mac_dbdma.h").read_text(encoding="utf-8")
macio = (ROOT / "hw/misc/macio/macio.c").read_text(encoding="utf-8")
qtest = (ROOT / "tests/qtest/macio-timer-test.c").read_text(encoding="utf-8")
screamer = (ROOT / "hw/audio/screamer.c").read_text(encoding="utf-8")
ide = (ROOT / "hw/ide/macio.c").read_text(encoding="utf-8")

for token in ('#define RUN        0x8000', '#define ACTIVE     0x0400',
              '#define DBDMA_CMDPTR_LO       0x03',
              '#define DBDMA_STATUS          0x01',
              '#define OUTPUT_LAST     0x1000'):
    assert token in header, token

out = dma.split("static void start_output(", 1)[1].split(
    "static void start_input(", 1)[0]
inn = dma.split("static void start_input(", 1)[1].split(
    "static void load_word(", 1)[0]
for fn in (out, inn):
    assert "if (key > KEY_STREAM3) {" in fn
    assert "if (!addr ||" not in fn
    assert "ch->io.addr = addr;" in fn

write = dma.split("static void dbdma_write(", 1)[1].split(
    "static uint64_t dbdma_read(", 1)[0]
assert "(ch->regs[DBDMA_STATUS] & (RUN | ACTIVE))" in write
assert "if (reg == DBDMA_STATUS) {" in write
assert write.index("if (reg == DBDMA_STATUS) {") < write.index(
    "ch->regs[reg] = value;")
assert "ch->regs[DBDMA_CMDPTR_LO] &= ~0xf;" in write

assert 'memory_region_add_subregion(&s->bar, 0x08000,' in macio
assert "macio_screamer_register_dma(&ns->screamer, &s->dbdma, 0x10, 0x12);" in macio
assert "screamer_tx_refill(s, io);" in screamer
assert "macio_ide_register_dma" in ide
for token in (
    "static void test_sawtooth_dbdma_registers(",
    "static void test_sawtooth_dbdma_zero_address(",
    "map_sawtooth_keylargo(qts);",
    "0xc000c000U",
    "0xffffffffU",
    "stw_le_p(descriptor + 2, 0x1000);",
    "stl_le_p(descriptor + 4, 0);",
    '"/ppc/macio/sawtooth-dbdma-registers"',
    '"/ppc/macio/sawtooth-dbdma-zero-address"',
):
    assert token in qtest, token

print("Sawtooth KeyLargo DB-DMA address/control contract: verified")
