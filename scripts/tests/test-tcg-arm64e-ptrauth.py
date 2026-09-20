#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tcg_core = (ROOT / 'tcg/tcg.c').read_text(encoding='utf-8')
tcg_aarch64 = (ROOT / 'tcg/aarch64/tcg-target.c.inc').read_text(encoding='utf-8')
cpu_exec = (ROOT / 'accel/tcg/cpu-exec.c').read_text(encoding='utf-8')
policy = (ROOT / 'scripts/macos-arch-policy.bash').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

# arm64e has three TCG pointer-authentication boundaries: JIT -> C helper
# calls, C -> JIT entry, and the generated JIT return path.  Keep helper
# normalization in generic TCG code so every AArch64 helper call path, including
# qemu_ld/st slow paths, receives the same raw C code address before the backend
# chooses BL/BLR.
#
# Ordinary C function pointers use ptrauth_key_function_pointer with a zero
# discriminator.  A cast through void * does not strip or re-sign the pointer,
# so TCG must do both transitions explicitly.
helper_ready = all(token in tcg_core for token in (
    '#include <ptrauth.h>',
    '#if defined(__PTRAUTH__)',
    'ptrauth_key_function_pointer',
    'ptrauth_strip(func, ptrauth_key_function_pointer)',
    'tcg_ptrauth_init_ldst_helpers();',
    'qemu_ld_helpers[i] = tcg_ptrauth_strip_helper(qemu_ld_helpers[i]);',
    'qemu_st_helpers[i] = tcg_ptrauth_strip_helper(qemu_st_helpers[i]);',
    'tcg_out_call(s, tcg_ptrauth_strip_helper(tcg_call_func(op)), info);',
))
entry_ready = all(token in tcg_core for token in (
    'ptrauth_sign_unauthenticated',
    'tcg_qemu_tb_exec = tcg_ptrauth_sign_jit_entry(',
)) and re.search(
    r'ptrauth_sign_unauthenticated\s*\(\s*\(tcg_prologue_fn \*\)entry\s*,'
    r'\s*ptrauth_key_function_pointer\s*,\s*0\s*\)',
    tcg_core,
    re.S,
)
return_ready = all(token in tcg_aarch64 for token in (
    'PACIBSP           = 0xd503237f',
    'RETAB             = 0xd65f0fff',
    'tcg_out32(s, PACIBSP);',
    'tcg_out32(s, RETAB);',
)) and re.search(
    r'tcg_out_bti\(s, BTI_C\);.*?'
    r'#if defined\(__PTRAUTH__\).*?'
    r'tcg_out32\(s, PACIBSP\);.*?'
    r'tcg_out_insn\(s, ldstpair, STP, TCG_REG_FP, TCG_REG_LR,.*?'
    r'tcg_out_insn\(s, ldstpair, LDP, TCG_REG_FP, TCG_REG_LR,.*?'
    r'#if defined\(__PTRAUTH__\).*?'
    r'tcg_out32\(s, RETAB\);.*?'
    r'#else.*?'
    r'tcg_out_insn\(s, bcond_reg, RET, TCG_REG_LR\);',
    tcg_aarch64,
    re.S,
)
runtime_ready = all(token in workflow for token in (
    'WHP_MACOS_ARCH: arm64e',
    'qemu-system-i386',
    'lipo -archs',
    'xcrun -f ld',
    'scripts/bench-i386-tcg.py',
    '--workload startup',
    '--workload fcomi',
    '--tcg-thread single',
))

assert helper_ready, 'arm64e JIT -> C helper calls are not pointer-auth safe'
assert entry_ready, 'arm64e C -> JIT entry is not signed as a C function pointer'
assert return_ready, 'arm64e TCG prologue/epilogue does not authenticate LR'
assert runtime_ready, 'macOS CI does not execute an arm64e TCG runtime smoke test'

# PAC work belongs at setup/translation boundaries, not the per-TB dispatcher.
assert 'ptrauth_strip' not in cpu_exec
assert 'ptrauth_sign_unauthenticated' not in cpu_exec

# Promotion of WHP_MACOS_ARCH=auto remains a separate policy decision made only
# after the implementation and runtime lane above are both present and green.
assert 'whp_select_macos_arch' in policy

print('arm64e TCG pointer-auth audit: calls, return path, and runtime smoke wired')
