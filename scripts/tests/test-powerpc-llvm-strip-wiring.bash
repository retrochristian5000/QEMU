#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
strip_stage="$ROOT/scripts/bootstrap-powerpc-llvm-strip.sh"
orchestrator="$ROOT/scripts/bootstrap-powerpc-clang.sh"

grep -Fq 'STRIP_SCHEMA=2' "$strip_stage"
grep -Fq 'GNU_STRIP=disabled' "$strip_stage"
grep -Fq 'rm -f "$shim_dir/strip" "$shim_dir/strip.bfd"' "$strip_stage"
grep -Fq 'ln -s "../llvm/bin/llvm-strip" "$public_strip"' "$strip_stage"
grep -Fq 'ln -s "../../bin/${TOOLCHAIN_TARGET}-strip" "$target_strip"' "$strip_stage"
if grep -Fq 'gnu_strip=' "$strip_stage" ||
   grep -Fq 'Private GNU strip oracle' "$strip_stage" ||
   grep -Fq 'mv "$public_strip" "$gnu_strip"' "$strip_stage"; then
    printf 'error: LLVM strip stage still retains a GNU strip fallback\n' >&2
    exit 1
fi

grep -Fq 'bootstrap-powerpc-llvm-strip.sh' "$orchestrator"

printf 'PowerPC LLVM strip wiring: verified\n'
