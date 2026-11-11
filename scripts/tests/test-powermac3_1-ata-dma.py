#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard MacIO ATA DMA read/write vs ATAPI completion callbacks.

The classic Mac OS Installer may rewrite Apple_Driver_ATA partitions. ATA
completion must not accidentally use the CD-ROM/ATAPI completion routine.
"""

from pathlib import Path

SOURCE = Path(__file__).resolve().parents[2] / "hw/ide/macio.c"
src = SOURCE.read_text(encoding="utf-8")

atapi_start = src.index('static void pmac_ide_atapi_transfer_cb(')
ata_start = src.index('static void pmac_ide_transfer_cb(')
dispatch_end = src.index('static void pmac_ide_transfer(DBDMA_io *io)',
                         ata_start)
atapi = src[atapi_start:ata_start]
ata = src[ata_start:dispatch_end]

# ATAPI CD-ROM path retains its packet-command completion and 2048-byte LBAs.
assert "ide_atapi_cmd_ok(s);" in atapi
assert "ide_atapi_io_error(s, ret);" in atapi
assert "((int64_t)s->lba << 11)" in atapi
assert "pmac_ide_atapi_transfer_cb, io);" in atapi

# Hard disks use the 512-byte LBA and ATA status/IRQ/error lifecycle.
assert "ide_get_sector(s) << 9" in ata
assert "ide_dma_error(s);" in ata
assert "ide_bus_set_irq(s->bus);" in ata
assert "s->status = READY_STAT | SEEK_STAT;" in ata

def case_block(label: str, next_label: str) -> str:
    return ata.split(label, 1)[1].split(next_label, 1)[0]

read = case_block("case IDE_DMA_READ:", "case IDE_DMA_WRITE:")
write = case_block("case IDE_DMA_WRITE:", "case IDE_DMA_TRIM:")
trim = ata.split("case IDE_DMA_TRIM:", 1)[1].split("default:", 1)[0]

assert "dma_blk_read(s->blk" in read
assert "pmac_ide_transfer_cb, io);" in read
assert "pmac_ide_atapi_transfer_cb" not in read
assert "dma_blk_write(s->blk" in write
assert "pmac_ide_transfer_cb, io);" in write
assert "ide_issue_trim" in trim
assert "pmac_ide_transfer_cb, io," in trim

# ATAPI and ATA must remain separate paths at the initial DBDMA dispatch.
initial = src[dispatch_end:src.index("static void pmac_ide_flush(", dispatch_end)]
assert "if (s->drive_kind == IDE_CD)" in initial
assert "pmac_ide_atapi_transfer_cb(io, 0);" in initial
assert "pmac_ide_transfer_cb(io, 0);" in initial

print("MacIO ATA/ATAPI DMA callback dispatch: verified")
