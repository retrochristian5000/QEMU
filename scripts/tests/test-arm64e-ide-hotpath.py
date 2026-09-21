#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
core = (ROOT / "hw/ide/core.c").read_text(encoding="utf-8")

required = (
    "static void ide_set_end_transfer_func(IDEState *s, EndTransferFunc *fn)",
    "s->end_transfer_fn_idx = idx;",
    "switch (s->end_transfer_fn_idx)",
    "[IDE_TRANSFER_END_SECTOR_READ] = ide_sector_read",
    "[IDE_TRANSFER_END_SECTOR_WRITE] = ide_sector_write",
    "[IDE_TRANSFER_END_STOP] = ide_transfer_stop",
    "[IDE_TRANSFER_END_ATAPI_REPLY] = ide_atapi_cmd_reply_end",
    "[IDE_TRANSFER_END_ATAPI_CMD] = ide_atapi_cmd",
    "[IDE_TRANSFER_END_DUMMY_STOP] = ide_dummy_transfer_stop",
)

for token in required:
    assert token in core, f"missing IDE hot-path contract: {token}"

start = core.index("static bool ide_is_pio_out(IDEState *s)")
end = core.index("\n}\n", start) + 3
pio = core[start:end]

assert "end_transfer_func ==" not in pio, (
    "IDE PIO direction regressed to per-access function-pointer comparisons"
)
assert "end_transfer_func !=" not in pio, (
    "IDE PIO direction regressed to per-access function-pointer comparisons"
)

print("ARM64e IDE PIO hot-path audit passed")
