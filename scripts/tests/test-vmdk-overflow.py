#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
VMDK = ROOT / 'block' / 'vmdk.c'

source = VMDK.read_text(encoding='utf-8')

# The VMDK L1 table allocation is sized in host size_t units.  Keep the
# multiplication on GLib's checked-size helper rather than an undefined
# generic mul_overflow() spelling.
assert 'mul_overflow(' not in source
assert 'extent->entry_size <= 0 ||' in source
assert '!g_size_checked_mul(&l1_size, (size_t)extent->l1_size,' in source
assert '(size_t)extent->entry_size))' in source

match = re.search(
    r'static int GRAPH_RDLOCK\s+vmdk_init_tables\('
    r'.*?g_try_malloc\(l1_size\)',
    source,
    re.S,
)
assert match is not None
body = match.group(0)
assert body.index('g_size_checked_mul') < body.index('g_try_malloc(l1_size)')

print('VMDK checked multiplication policy: passed')
