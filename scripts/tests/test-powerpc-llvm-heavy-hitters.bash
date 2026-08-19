#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BASE="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
CORE="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"

for file in "$BASE" "$CORE"; do
    if [[ ! -f "$file" ]]; then
        printf 'error: required LLVM bootstrap script is missing: %s\n' "$file" >&2
        exit 1
    fi
done

# Heavy build-cost knobs must be explicit and validated. Link parallelism is
# scheduling policy; accuracy checks are semantic because they change the built
# compiler and therefore belong in the toolchain marker.
grep -Fq 'LLVM_ACCURACY_CHECKS="${POWERPC_LLVM_ACCURACY_CHECKS:-0}"' "$BASE"
grep -Fq 'LLVM_LINK_JOBS="${POWERPC_LLVM_LINK_JOBS:-2}"' "$BASE"
grep -Fq 'POWERPC_LLVM_ACCURACY_CHECKS must be 0 or 1' "$BASE"
grep -Fq 'POWERPC_LLVM_LINK_JOBS must be a positive integer' "$BASE"
grep -Fq 'llvm_enable_assertions=OFF' "$BASE"
grep -Fq 'llvm_optimized_tablegen=OFF' "$BASE"
grep -Fq 'llvm_enable_assertions=ON' "$BASE"
grep -Fq 'llvm_optimized_tablegen=ON' "$BASE"

# Fast-hardened default: avoid VCS-wide relinks and unused analyzer code, make
# release-mode unreachable paths trap deterministically, and keep heavyweight
# link concurrency in its own Ninja pool.
grep -Fq -- '-DLLVM_APPEND_VC_REV=OFF' "$BASE"
grep -Fq -- '-DCLANG_ENABLE_STATIC_ANALYZER=OFF' "$BASE"
grep -Fq -- '-DLLVM_UNREACHABLE_OPTIMIZE=OFF' "$BASE"
grep -Fq -- '"-DLLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS"' "$BASE"
grep -Fq -- '"-DLLVM_ENABLE_ASSERTIONS=$llvm_enable_assertions"' "$BASE"
grep -Fq -- '"-DLLVM_OPTIMIZED_TABLEGEN=$llvm_optimized_tablegen"' "$BASE"

# The accuracy profile changes generated tools and must invalidate the semantic
# marker exactly once. Link-pool sizing must never do so.
grep -Fq 'BOOTSTRAP_SCHEMA=19' "$BASE"
grep -Fq 'LLVM_ACCURACY_CHECKS=$LLVM_ACCURACY_CHECKS' "$BASE"
grep -Fq 'LLVM_ENABLE_ASSERTIONS=$llvm_enable_assertions' "$BASE"
grep -Fq 'LLVM_OPTIMIZED_TABLEGEN=$llvm_optimized_tablegen' "$BASE"
if grep -Fq 'LLVM_LINK_JOBS=' "$BASE"; then
    printf 'error: link scheduling leaked into the base semantic marker\n' >&2
    exit 1
fi

# Standalone LLD must stay in the same assertion/ABI-check mode as the base LLVM
# libraries it consumes. Its link pool is also scheduling-only.
grep -Fq 'LLVM_LINK_JOBS="${POWERPC_LLVM_LINK_JOBS:-2}"' "$CORE"
grep -Fq 'lld_llvm_enable_assertions=' "$CORE"
grep -Fq 'lld_llvm_optimized_tablegen=' "$CORE"
grep -Fq '"-DLLVM_ENABLE_ASSERTIONS=$lld_llvm_enable_assertions"' "$CORE"
grep -Fq '"-DLLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS"' "$CORE"
grep -Fq 'LLD_SCHEMA=6' "$CORE"
grep -Fq 'LLVM_ENABLE_ASSERTIONS=$lld_llvm_enable_assertions' "$CORE"
grep -Fq 'LLVM_OPTIMIZED_TABLEGEN=$lld_llvm_optimized_tablegen' "$CORE"
if grep -Fq 'LLVM_LINK_JOBS=' "$CORE"; then
    printf 'error: link scheduling leaked into the LLD semantic marker\n' >&2
    exit 1
fi

printf 'PowerPC LLVM heavy-hitter policy: verified\n'
