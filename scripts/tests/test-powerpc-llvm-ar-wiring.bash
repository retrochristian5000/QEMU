#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ar_stage="$ROOT/scripts/bootstrap-powerpc-llvm-ar.sh"
core="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
nm_stage="$ROOT/scripts/bootstrap-powerpc-llvm-nm.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"

grep -Fq 'AR_SCHEMA=2' "$ar_stage"
grep -Fq 'AR=llvm-ar' "$ar_stage"
grep -Fq 'GNU_AR=disabled' "$ar_stage"
grep -Fq '"$clang" --target=powerpc-none-elf -c -x assembler' "$ar_stage"
grep -Fq '"$llvm_ar" rcs "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq '"$llvm_ar" t "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq '"$llvm_ar" p "$smoke_dir/libarchive.a" archive.o' "$ar_stage"
grep -Fq '"$llvm_nm" --gnu-compatible -s "$smoke_dir/libarchive.a"' "$ar_stage"
grep -Fq 'rm -f "$shim_dir/ar" "$shim_dir/ar.bfd"' "$ar_stage"
grep -Fq 'ln -s "../llvm/bin/llvm-ar" "$public_ar"' "$ar_stage"
grep -Fq 'ln -s "../../bin/${TOOLCHAIN_TARGET}-ar" "$target_ar"' "$ar_stage"

if grep -Fq 'exec "$llvm_ar"' "$ar_stage" ||
   grep -Fq 'Retained GNU ar' "$ar_stage" ||
   grep -Fq 'mv "$public_ar"' "$ar_stage" ||
   grep -Fq 'public_ld=' "$ar_stage" ||
   grep -Fq 'public_as=' "$ar_stage"; then
    printf 'error: LLVM ar stage still depends on a post-base/GNU archive path\n' >&2
    exit 1
fi

grep -Fq 'bootstrap-powerpc-llvm-ar.sh' "$orchestrator"
grep -Fq 'No private GNU as/ar/nm/strip fallbacks survive' "$orchestrator"
grep -Fq 'POWERPC_TOOLCHAIN_FORCE_REBUILD=0' "$orchestrator"

base_line="$(grep -nF 'bash "$BASE_BOOTSTRAP"' "$orchestrator" | head -n1 | cut -d: -f1)"
ar_line="$(grep -nF 'bootstrap-powerpc-llvm-ar.sh' "$orchestrator" | tail -n1 | cut -d: -f1)"
core_line="$(grep -nF 'bootstrap-powerpc-clang-core.sh' "$orchestrator" | tail -n1 | cut -d: -f1)"
as_line="$(grep -nF 'bootstrap-powerpc-llvm-as.sh' "$orchestrator" | tail -n1 | cut -d: -f1)"
nm_line="$(grep -nF 'bootstrap-powerpc-llvm-nm.sh' "$orchestrator" | tail -n1 | cut -d: -f1)"
if (( ar_line <= base_line || core_line <= ar_line || as_line <= core_line || nm_line <= as_line )); then
    printf 'error: LLVM ar must be published after base and before LLD/IAS/nm\n' >&2
    exit 1
fi

# The LLD core smoke already archives a PowerPC object through the public
# target-prefixed ar. Since the orchestrator publishes llvm-ar first, this is
# the cross-stage proof that LLD consumes LLVM's archive implementation.
grep -Fq '"$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar" rcs' "$core"

# nm's archive-map qualification must consume the already-published LLVM ar
# route rather than falling back to a GNU archiver.
grep -Fq 'public_ar="$TOOLCHAIN_DIR/bin/${TOOLCHAIN_TARGET}-ar"' "$nm_stage"
grep -Fq '"$public_ar" rcs "$smoke_dir/libnm.a"' "$nm_stage"

printf 'PowerPC LLVM ar wiring: verified\n'
