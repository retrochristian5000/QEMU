#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
base="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
as_stage="$ROOT/scripts/bootstrap-powerpc-llvm-as.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"

# GNU binutils may still provide the temporary linker and object utilities,
# but GAS must never be configured, installed, retained, or selected.
grep -Fq -- '--disable-gas' "$base"
grep -Fq 'GNU_GAS=disabled' "$base"
if grep -Fq -- '-fno-integrated-as' "$base"; then
    printf 'error: PowerPC Clang wrapper still disables the integrated assembler\n' >&2
    exit 1
fi
if grep -Fq 'for tool in gcc as ar ld' "$base" ||
   grep -Fq 'for tool in as ar ld' "$base"; then
    printf 'error: PowerPC base toolchain still requires GNU as\n' >&2
    exit 1
fi
if grep -Fq 'ln -sf "../../bin/${TOOLCHAIN_TARGET}-as" "$shim_dir/as"' "$base"; then
    printf 'error: base bootstrap still wires a private GNU assembler shim\n' >&2
    exit 1
fi

grep -Fq 'LLD_SCHEMA=2' "$core"
grep -Fq 'ASSEMBLER=clang-integrated' "$core"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$core"
if grep -Fq 'Retained assembler: GNU as' "$core"; then
    printf 'error: LLD stage still declares GNU as as retained\n' >&2
    exit 1
fi

grep -Fq 'ASSEMBLER_SCHEMA=3' "$as_stage"
grep -Fq 'GNU_GAS=disabled' "$as_stage"
grep -Fq 'exec "$clang" --target=powerpc-none-elf -c -x assembler' "$as_stage"
if grep -Fq 'gnu_as=' "$as_stage" ||
   grep -Fq 'Retained GNU assembler oracle' "$as_stage" ||
   grep -Fq 'mv "$public_as" "$gnu_as"' "$as_stage"; then
    printf 'error: LLVM assembler stage still retains a GNU as fallback\n' >&2
    exit 1
fi

grep -Fq 'GNU as is not built or retained' "$orchestrator"

printf 'PowerPC LLVM assembler wiring: verified\n'
