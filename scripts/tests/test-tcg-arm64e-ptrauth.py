#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tcg_core = (ROOT / 'tcg/tcg.c').read_text(encoding='utf-8')
policy = (ROOT / 'scripts/macos-arch-policy.bash').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

# arm64e has two TCG pointer-authentication boundaries.  Keep the bridge in
# generic TCG code so every AArch64 helper call path, including qemu_ld/st slow
# paths, receives the same raw C code address before the backend chooses BL/BLR.
#
# Ordinary C function pointers use ptrauth_key_function_pointer with a zero
# discriminator.  A cast through void * does not strip or re-sign the pointer,
# so TCG must do both transitions explicitly.
helper_ready = all(token in tcg_core for token in (
    '#include <ptrauth.h>',
    '__PTRAUTH__',
    'ptrauth_key_function_pointer',
    'ptrauth_strip',
    'qemu_ld_helpers',
    'qemu_st_helpers',
    'tcg_out_call',
))
entry_ready = all(token in tcg_core for token in (
    '#include <ptrauth.h>',
    '__PTRAUTH__',
    'ptrauth_key_function_pointer',
    'ptrauth_sign_unauthenticated',
    'tcg_qemu_tb_exec',
)) and re.search(
    r'ptrauth_sign_unauthenticated\s*\([^;]*?'
    r'ptrauth_key_function_pointer\s*,\s*0\s*\)',
    tcg_core,
    re.S,
)
runtime_ready = all(token in workflow for token in (
    'WHP_MACOS_ARCH: arm64e',
    'qemu-system-i386',
    'lipo -archs',
    'scripts/bench-i386-tcg.py',
    '--workload startup',
    '--tcg-thread single',
))

assert helper_ready, 'arm64e JIT -> C helper calls are not pointer-auth safe'
assert entry_ready, 'arm64e C -> JIT entry is not signed as a C function pointer'
assert runtime_ready, 'macOS CI does not execute an arm64e TCG runtime smoke test'

# Promotion of WHP_MACOS_ARCH=auto remains a separate policy decision made only
# after the implementation and runtime lane above are both present and green.
assert 'whp_select_macos_arch' in policy

print('arm64e TCG pointer-auth audit: implementation and runtime smoke required')
