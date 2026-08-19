#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ldscript="$ROOT/roms/openbios/arch/ppc/qemu/ldscript"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
build="$ROOT/scripts/build-openbios.sh"

if [[ ! -f "$ldscript" ]]; then
    printf 'error: OpenBIOS submodule is not initialized: %s\n' "$ldscript" >&2
    exit 1
fi

# In an ELF32 PowerPC image, aligning the location counter after a four-byte
# reset vector at 0xfffffffc produces 0x100000000.  That value truncates to
# zero in the ELF32 symbol table.  _end must describe the end of the normal
# firmware payload before the detached hard-reset vector instead.
end_line="$(grep -nE '^[[:space:]]*_end[[:space:]]*=[[:space:]]*\.;' "$ldscript" | cut -d: -f1)"
hreset_line="$(grep -nE '^[[:space:]]*\.[[:space:]]*=[[:space:]]*HRESET_ADDR;' "$ldscript" | cut -d: -f1)"
if [[ -z "$end_line" || -z "$hreset_line" || "$end_line" -ge "$hreset_line" ]]; then
    printf 'error: OpenBIOS _end is not defined before the hard-reset vector\n' >&2
    exit 1
fi
grep -Fq 'ASSERT(_end <= HRESET_ADDR' "$ldscript"
if grep -Fq '. = ALIGN(4096);' "$ldscript" &&
   tail -n "+$hreset_line" "$ldscript" | grep -Fq '_end = .;'; then
    printf 'error: OpenBIOS still derives _end by aligning past 0xffffffff\n' >&2
    exit 1
fi

# Keep the bootstrap smoke structurally equivalent to the real linker script
# and make the real firmware validator reject an impossible/wrapped end symbol.
grep -Fq 'ASSERT(_end <= HRESET_ADDR' "$core"
grep -Fq 'LLD changed the OpenBIOS payload end symbol' "$core"
grep -Fq 'OpenBIOS _end symbol is missing or outside the normal PROM payload' "$build"

printf 'OpenBIOS linker end-symbol policy: verified\n'
