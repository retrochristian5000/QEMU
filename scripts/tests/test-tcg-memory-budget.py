#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Source-level regression gates for automatic TCG sizing and Darwin JIT VM."""
from pathlib import Path
import re

root = Path(__file__).resolve().parents[2]
accel = (root / "accel/tcg/tcg-all.c").read_text(encoding="utf-8")
region = (root / "tcg/region.c").read_text(encoding="utf-8")

# The automatic system-mode TCG cache must account for guest RAM as well as
# host RAM. Explicit user-configured tb-size must remain untouched.
assert "size_t tb_size = s->tb_size * MiB;" in accel
assert "if (s->tb_size == 0 && ms->ram_size != 0)" in accel
assert "host_ram ? host_ram / 8 : 1 * GiB" in accel
assert "MAX(64 * MiB," in accel
assert "MIN(ms->ram_size / 4," in accel
assert "tb_size = MIN(host_limit, guest_limit);" in accel
assert "QEMU_ALIGN_DOWN(tb_size, qemu_real_host_page_size())" in accel
assert "tcg_init(tb_size, s->splitwx_enabled, max_threads);" in accel

# Illustrative policy calculations: MiB units, excluding architecture-specific
# final caps. This is not a substitute for a native runtime/RSS test.
def auto_cache_mib(host_ram_mib: int, guest_ram_mib: int) -> int:
    host_limit = host_ram_mib // 8 if host_ram_mib else 1024
    guest_limit = max(64, guest_ram_mib // 4)
    return max(1, min(host_limit, guest_limit))

assert auto_cache_mib(8192, 256) == 64
assert auto_cache_mib(8192, 16) == 64
assert auto_cache_mib(8192, 2048) == 512
assert auto_cache_mib(8192, 8192) == 1024
assert auto_cache_mib(2048, 8192) == 256
assert auto_cache_mib(0, 256) == 64

# alloc_code_gen_buffer_anon returns a protection mask on success and -1 on
# failure. !return_value is incorrect: !-1 is false, so a failed mmap would
# continue to mach_vm_remap with an invalid source mapping.
assert "if (!alloc_code_gen_buffer_anon" not in region
assert re.search(
    r"if \\(alloc_code_gen_buffer_anon\\(size, PROT_READ \\| PROT_WRITE,"
    r".*?MAP_PRIVATE \\| MAP_ANONYMOUS, errp\\) < 0\\) \\{"
    r"\\s*return -1;",
    region,
    re.S,
)
print("TCG memory-budget and Darwin JIT allocation source checks passed")
