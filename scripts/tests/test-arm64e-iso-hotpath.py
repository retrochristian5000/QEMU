#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
io = (ROOT / "block/io.c").read_text(encoding="utf-8")
raw = (ROOT / "block/raw-format.c").read_text(encoding="utf-8")
header = (ROOT / "include/block/block_int-io.h").read_text(encoding="utf-8")
ide = (ROOT / "tests/qtest/ide-test.c").read_text(encoding="utf-8")

for token in (
    "int coroutine_fn GRAPH_RDLOCK bdrv_raw_co_preadv(",
    "if (likely(drv == &bdrv_raw))",
    "ret = bdrv_raw_co_preadv(bs, offset, bytes, qiov, flags);",
):
    assert token in header + io, f"missing raw ISO direct-read contract: {token}"

for token in (
    "bdrv_raw_co_preadv(BlockDriverState *bs",
    "ret = raw_adjust_offset(bs, &offset, bytes, false);",
    "BLKDBG_CO_EVENT(bs->file, BLKDBG_READ_AIO);",
    "return bdrv_co_preadv(bs->file, offset, bytes, qiov, flags);",
    ".bdrv_co_preadv       = &bdrv_raw_co_preadv,",
):
    assert token in raw, f"raw ISO semantics changed or fast path missing: {token}"

start = io.index("bdrv_driver_preadv(")
end = io.index("\n}\n", start) + 3
dispatch = io[start:end]
assert dispatch.index("if (drv->bdrv_co_preadv_part)") < dispatch.index(
    "if (likely(drv == &bdrv_raw))"
), "partial-read handlers must take precedence over the raw direct path"
assert "ret = drv->bdrv_co_preadv(bs, offset, bytes, qiov, flags);" in dispatch

for test_name in (
    '"/ide/cdrom/pio"',
    '"/ide/cdrom/pio_large"',
    '"/ide/cdrom/dma"',
):
    assert test_name in ide, f"missing ATAPI raw-CD regression coverage: {test_name}"

assert "media=cdrom,format=raw" in ide
assert "send_scsi_cdb_read10" in ide

print("ARM64e raw ISO read hot-path audit passed")
