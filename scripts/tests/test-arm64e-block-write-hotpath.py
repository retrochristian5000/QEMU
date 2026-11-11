#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
io = (ROOT / "block/io.c").read_text(encoding="utf-8")
raw = (ROOT / "block/raw-format.c").read_text(encoding="utf-8")
file_posix = (ROOT / "block/file-posix.c").read_text(encoding="utf-8")
header = (ROOT / "include/block/block_int-io.h").read_text(encoding="utf-8")

for token in ("bdrv_raw_co_pwritev(", "bdrv_file_co_pwritev("):
    assert token in header, f"missing direct block-write declaration: {token}"

start = io.index("bdrv_driver_pwritev(")
end = io.index(
    "static int coroutine_fn GRAPH_RDLOCK\nbdrv_driver_pwritev_compressed", start
)
dispatch = io[start:end]

assert dispatch.index("if (drv->bdrv_co_pwritev_part)") < dispatch.index(
    "if (likely(drv == &bdrv_raw))"
), "partial-write handlers must take precedence over the raw direct path"
assert dispatch.index("if (likely(drv == &bdrv_raw))") < dispatch.index(
    "if (drv->bdrv_co_pwritev)"
), "raw writes must bypass generic callback dispatch"
assert "ret = bdrv_raw_co_pwritev(bs, offset, bytes, qiov, flags);" in dispatch
assert "#ifdef CONFIG_POSIX" in dispatch
assert "if (likely(drv == &bdrv_file))" in dispatch
assert "ret = bdrv_file_co_pwritev(bs, offset, bytes, qiov, flags);" in dispatch

for token in (
    "bdrv_raw_co_pwritev(BlockDriverState *bs",
    "ret = raw_adjust_offset(bs, &offset, bytes, true);",
    "BLKDBG_CO_EVENT(bs->file, BLKDBG_WRITE_AIO);",
    "ret = bdrv_co_pwritev(bs->file, offset, bytes, qiov, flags);",
    ".bdrv_co_pwritev      = &bdrv_raw_co_pwritev,",
):
    assert token in raw, f"raw-format write semantics changed: {token}"

for token in (
    "bdrv_file_co_pwritev(BlockDriverState *bs",
    "return raw_co_prw(bs, &offset, bytes, qiov, QEMU_AIO_WRITE, flags);",
    ".bdrv_co_pwritev        = bdrv_file_co_pwritev,",
):
    assert token in file_posix, f"POSIX file write semantics changed: {token}"

assert dispatch.index("if (ret == 0 && emulate_fua)") > dispatch.index(
    "if (likely(drv == &bdrv_file))"
), "FUA emulation moved ahead of the direct write path"

print("ARM64e block write hot-path audit passed")
