#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tcg = (ROOT / 'tcg/aarch64/tcg-target.c.inc').read_text(encoding='utf-8')
tcg_core = (ROOT / 'tcg/tcg.c').read_text(encoding='utf-8')
policy = (ROOT / 'scripts/macos-arch-policy.bash').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

# arm64e has two TCG pointer-authentication boundaries:
#   JIT -> C: signed C helper pointers must become raw code addresses before
#             plain TCG BL/BLR emission.
#   C -> JIT: raw generated-code addresses must be signed before C calls them
#             through tcg_qemu_tb_exec's function-pointer type.
helper_ready = (
    '#include <ptrauth.h>' in tcg
    and 'ptrauth_key_function_pointer' in tcg
    and 'ptrauth_strip' in tcg
)
entry_ready = (
    '#include <ptrauth.h>' in tcg_core
    and 'ptrauth_sign_unauthenticated' in tcg_core
    and 'tcg_qemu_tb_exec' in tcg_core
)
runtime_ready = all(token in workflow for token in (
    'arm64e-tcg-bios.bin',
    'isa-debug-exit',
    '-accel tcg',
    'tcg_status',
    '[[ "$tcg_status" -eq 85 ]]',
))

if helper_ready and entry_ready and runtime_ready:
    # Once all three pieces exist, auto may be promoted to arm64e in a later
    # policy change.  This test intentionally does not force that promotion.
    print('arm64e TCG pointer-auth audit: implementation and runtime smoke present')
else:
    # Until the complete bridge is present, the default must remain arm64.
    assert 'Keep auto on the established' in policy
    auto_start = policy.index('if [[ "$requested" == auto ]]')
    auto_end = policy.index('\n    fi', auto_start)
    auto_body = policy[auto_start:auto_end]
    assert 'printf \'%s\\n\' "$native_arch"' in auto_body
    assert 'arm64e\\n' not in auto_body
    print('arm64e TCG pointer-auth audit: gap recorded; auto remains arm64')
