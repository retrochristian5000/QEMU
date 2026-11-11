#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ldscript="$ROOT/roms/openbios/arch/ppc/qemu/ldscript"

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
if tail -n "+$hreset_line" "$ldscript" | grep -Fq '_end = .;'; then
    printf 'error: OpenBIOS still derives _end after the hard-reset vector\n' >&2
    exit 1
fi

# Exercise the real linker script when an LLVM PowerPC assembler/linker and
# ordinary ELF inspection tools are available.  Source-only environments keep
# the structural guard above; CI installs these tools and therefore takes the
# behavioral path too.
clang="$(command -v clang 2>/dev/null || true)"
lld="$(command -v ld.lld 2>/dev/null || true)"
readelf_cmd="$(command -v llvm-readelf 2>/dev/null || command -v readelf 2>/dev/null || true)"
nm_cmd="$(command -v llvm-nm 2>/dev/null || command -v nm 2>/dev/null || true)"
if [[ -n "$clang" && -n "$lld" && -n "$readelf_cmd" && -n "$nm_cmd" ]]; then
    scratch="$(mktemp -d "${TMPDIR:-/tmp}/openbios-linker-layout.XXXXXX")"
    trap 'rm -rf "$scratch"' EXIT

    cat > "$scratch/layout.s" <<'ASSEMBLY'
.section .text.vectors,"ax",@progbits
.globl _entry
_entry:
    nop

.section .text,"ax",@progbits
.globl whp_payload
whp_payload:
    nop

.section .bss,"aw",@nobits
.space 16

.section .romentry,"ax",@progbits
.globl whp_hreset
whp_hreset:
    b _entry
ASSEMBLY
    "$clang" --target=powerpc-none-elf -c -x assembler \
        "$scratch/layout.s" -o "$scratch/layout.o"
    "$lld" --warn-common -z noexecstack -T "$ldscript" \
        -o "$scratch/layout.elf" "$scratch/layout.o"

    header="$(LC_ALL=C "$readelf_cmd" -hW "$scratch/layout.elf")"
    grep -Eq 'Class:[[:space:]]+ELF32' <<< "$header"
    grep -Eq "Data:[[:space:]]+2's complement, big endian" <<< "$header"
    grep -Eq 'Machine:[[:space:]]+PowerPC' <<< "$header"
    grep -Eq 'Entry point address:[[:space:]]+0xfff00100' <<< "$header"

    end_value="$(LC_ALL=C "$nm_cmd" "$scratch/layout.elf" |
        awk '$3 == "_end" {print tolower($1); exit}')"
    hreset_value="$(LC_ALL=C "$nm_cmd" "$scratch/layout.elf" |
        awk '$3 == "whp_hreset" {print tolower($1); exit}')"
    if [[ ! "$end_value" =~ ^[0-9a-f]+$ || "$end_value" == 00000000 ]]; then
        printf 'error: LLD produced an invalid OpenBIOS _end symbol: %s\n' \
            "${end_value:-missing}" >&2
        exit 1
    fi
    end_num=$((0x$end_value))
    if ((end_num < 0xfff08000 || end_num >= 0xfffffffc)); then
        printf 'error: OpenBIOS _end is outside the normal payload: %s\n' \
            "$end_value" >&2
        exit 1
    fi
    if [[ "$hreset_value" != fffffffc ]]; then
        printf 'error: OpenBIOS hard-reset vector moved: %s\n' \
            "${hreset_value:-missing}" >&2
        exit 1
    fi

    cat > "$scratch/overflow.s" <<'ASSEMBLY'
.section .text.vectors,"ax",@progbits
.globl _entry
_entry:
    nop
.section .bss,"aw",@nobits
.space 0x100000
.section .romentry,"ax",@progbits
    b _entry
ASSEMBLY
    "$clang" --target=powerpc-none-elf -c -x assembler \
        "$scratch/overflow.s" -o "$scratch/overflow.o"
    if "$lld" --warn-common -z noexecstack -T "$ldscript" \
        -o "$scratch/overflow.elf" "$scratch/overflow.o" \
        >"$scratch/overflow.log" 2>&1; then
        printf 'error: OpenBIOS linker accepted a payload overlapping reset space\n' >&2
        exit 1
    fi
    grep -Fq 'OpenBIOS payload overlaps hard reset vector' "$scratch/overflow.log"
fi

printf 'OpenBIOS linker end-symbol policy: verified\n'
