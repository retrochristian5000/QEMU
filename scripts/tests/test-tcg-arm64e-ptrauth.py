#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tcg = (ROOT / 'tcg/aarch64/tcg-target.c.inc').read_text(encoding='utf-8')
workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

# arm64e C function pointers carry a PAC. TCG helper calls are emitted by the
# JIT itself and the AArch64 backend may use plain BLR, so it must first turn
# the signed C function pointer into the raw code address used by that branch.
assert '#include <ptrauth.h>' in tcg
assert 'ptrauth_key_function_pointer' in tcg
assert 'ptrauth_strip' in tcg

call_start = tcg.index('static void tcg_out_call_int(')
call_end = tcg.index('\n}\n', call_start) + 3
call_body = tcg[call_start:call_end]
assert 'ptrauth_strip' in call_body
assert 'tcg_pcrel_diff' in call_body
assert call_body.index('ptrauth_strip') < call_body.index('tcg_pcrel_diff')

# The Apple-Silicon CI must execute translated guest code under the selected
# arm64e host ABI. --version alone does not enter TCG or exercise helper calls.
assert 'arm64e-tcg-bios.bin' in workflow
assert 'isa-debug-exit' in workflow
assert '-accel tcg' in workflow
assert 'tcg_status' in workflow
assert '[[ "$tcg_status" -eq 85 ]]' in workflow

print('arm64e TCG pointer-auth tests: passed')
