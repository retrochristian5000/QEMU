#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ar_stage="$ROOT/scripts/bootstrap-powerpc-llvm-ar.sh"
nm_stage="$ROOT/scripts/bootstrap-powerpc-llvm-nm.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"

grep -Fq 'AR_SCHEMA=1' "$ar_stage"
grep -Fq 'AR=llvm-ar' "$ar_stage"
grep -Fq 'GNU_AR=disabled' "$ar_stage"
grep -Fq '"$llvm_ar" rcs "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq '"$llvm_ar" t "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq '"$llvm_nm" --gnu-compatible -s "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq 'rm -f "$shim_dir/ar" "$shim_dir/ar.bfd"' "$ar_stage"
grep -Fq 'ln -s "../llvm/bin/llvm-ar" "$public_ar"' "$ar_stage"
grep -Fq 'ln -s "../../bin/${TOOLCHAIN_TARGET}-ar" "$target_ar"' "$ar_stage"

if grep -Fq 'exec "$llvm_ar"' "$ar_stage" ||
   grep -Fq 'Retained GNU ar' "$ar_stage" ||
   grep -Fq 'mv "$public_ar"' "$ar_stage"; then
    printf 'error: LLVM ar stage is wrapping or retaining a GNU ar fallback\n' >&2
    exit 1
fi

grep -Fq 'bootstrap-powerpc-llvm-ar.sh' "$orchestrator"
grep -Fq 'no private GNU as/ar/nm/strip fallbacks' "$orchestrator"

as_line="$(grep -nF 'bootstrap-powerpc-llvm-as.sh' "$orchestrator" | cut -d: -f1)"
ar_line="$(grep -nF 'bootstrap-powerpc-llvm-ar.sh' "$orchestrator" | cut -d: -f1)"
nm_line="$(grep -nF 'bootstrap-powerpc-llvm-nm.sh' "$orchestrator" | cut -d: -f1)"
if (( ar_line <= as_line || ar_line >= nm_line )); then
    printf 'error: LLVM ar stage must run after assembler and before nm\n' >&2
    exit 1
fi

# nm's archive-map qualification must now consume the already-published LLVM ar
# route rather than falling back to a GNU archiver.
grep -Fq 'public_ar="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar"' "$nm_stage"
grep -Fq '"$public_ar" rcs "$smoke_dir/libnm.a"' "$nm_stage"

printf 'PowerPC LLVM ar wiring: verified\n'
