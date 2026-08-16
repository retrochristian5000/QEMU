#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
nm_stage="$ROOT/scripts/bootstrap-powerpc-llvm-nm.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"

grep -Fq 'NM_SCHEMA=2' "$nm_stage"
grep -Fq 'NM=llvm-nm' "$nm_stage"
grep -Fq 'GNU_COMPATIBILITY=--gnu-compatible' "$nm_stage"
grep -Fq 'GNU_NM=disabled' "$nm_stage"
grep -Fq 'cat > "$public_nm"' "$nm_stage"
grep -Fq 'cat > "$target_nm"' "$nm_stage"
grep -Fq 'prefix=$(CDPATH= cd -P "$(dirname "$0")/.." && pwd)' "$nm_stage"
grep -Fq 'prefix=$(CDPATH= cd -P "$(dirname "$0")/../.." && pwd)' "$nm_stage"
grep -Fq 'exec "$llvm_nm" --gnu-compatible "$@"' "$nm_stage"
grep -Fq '"$llvm_nm" --gnu-compatible -s "$smoke_dir/libnm.a"' "$nm_stage"
grep -Fq '"$llvm_nm" --gnu-compatible -f Banana "$smoke_dir/nm.o"' "$nm_stage"
grep -Fq 'raw_exact="$("$llvm_nm" --gnu-compatible -A -g -n "$smoke_dir/nm.o")"' "$nm_stage"
grep -Fq 'public_exact="$("$public_nm" -A -g -n "$smoke_dir/nm.o")"' "$nm_stage"
grep -Fq 'target_exact="$("$target_nm" -A -g -n "$smoke_dir/nm.o")"' "$nm_stage"
grep -Fq 'check_linker_script_rejection raw "$llvm_nm" --gnu-compatible' "$nm_stage"
grep -Fq 'check_linker_script_rejection public "$public_nm"' "$nm_stage"
grep -Fq 'check_linker_script_rejection target "$target_nm"' "$nm_stage"
grep -Fq 'rm -f "$shim_dir/nm" "$shim_dir/nm.bfd"' "$nm_stage"
grep -Fq '[[ ! -L "$target_nm" ]] || return 1' "$nm_stage"

if grep -Fq 'ln -s "../../bin/${TOOLCHAIN_TARGET}-nm" "$target_nm"' "$nm_stage"; then
    printf 'error: target nm still symlinks to a path-sensitive shell launcher\n' >&2
    exit 1
fi

if grep -Fq 'mv "$public_nm"' "$nm_stage" ||
   grep -Fq 'Retained GNU nm' "$nm_stage"; then
    printf 'error: LLVM nm stage still retains a GNU nm fallback\n' >&2
    exit 1
fi

grep -Fq 'bootstrap-powerpc-llvm-nm.sh' "$orchestrator"
grep -Fq 'No private GNU as/ar/nm/strip fallbacks survive' "$orchestrator"

printf 'PowerPC LLVM nm wiring: verified\n'
