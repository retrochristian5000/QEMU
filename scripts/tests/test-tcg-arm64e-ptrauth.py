#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tcg = (ROOT / 'tcg/aarch64/tcg-target.c.inc').read_text(encoding='utf-8')
tcg_core = (ROOT / 'tcg/tcg.c').read_text(encoding='utf-8')
policy = (ROOT / 'scripts/macos-arch-policy.bash').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

# arm64e has two TCG pointer-authentication boundaries:
#   JIT -> C: C helper pointers carry the arm64e function-pointer signature,
#             but TCG emits plain BL/BLR instructions and therefore needs the
#             raw code address.
#   C -> JIT: generated code starts as a raw executable address, but C invokes
#             it through tcg_qemu_tb_exec's function-pointer type and therefore
#             needs a pointer signed with the default C function-pointer schema.
helper_ready = all(token in tcg for token in (
    '#include <ptrauth.h>',
    '__PTRAUTH__',
    'ptrauth_key_function_pointer',
    'ptrauth_strip',
    'tcg_out_call_int',
))
entry_ready = all(token in tcg_core for token in (
    '#include <ptrauth.h>',
    '__PTRAUTH__',
    'ptrauth_key_function_pointer',
    'ptrauth_function_pointer_type_discriminator(tcg_prologue_fn)',
    'ptrauth_sign_unauthenticated',
    'tcg_qemu_tb_exec',
))
runtime_ready = all(token in workflow for token in (
    'WHP_MACOS_ARCH: arm64e',
    'qemu-system-i386',
    'lipo -archs',
    'scripts/bench-i386-tcg.py',
    '--workload startup',
    '--tcg-thread single',
))

assert helper_ready, 'arm64e JIT -> C helper calls are not pointer-auth safe'
assert entry_ready, 'arm64e C -> JIT entry is not signed as a function pointer'
assert runtime_ready, 'macOS CI does not execute an arm64e TCG runtime smoke test'

# Promotion of WHP_MACOS_ARCH=auto must remain a separate policy decision made
# only after the implementation and runtime lane above are both present.
assert 'whp_select_macos_arch' in policy

print('arm64e TCG pointer-auth audit: implementation and runtime smoke required')
