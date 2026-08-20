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

marker_block()
{
    local file=$1
    awk '
        /expected(_lld)?_marker=.*cat <<MARKER/ { in_marker=1 }
        in_marker { print }
        in_marker && /^MARKER$/ { exit }
    ' "$file"
}

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

# OpenBIOS only needs the compiler, assembler path, LLVM object utilities, and
# focused LLD. Host plugin loading and rich crash/unwind diagnostics add code
# and dependencies to the bootstrap without changing generated firmware.
for flag in \
    '-DLLVM_ENABLE_PLUGINS=OFF' \
    '-DLLVM_ENABLE_BACKTRACES=OFF' \
    '-DLLVM_ENABLE_CRASH_OVERRIDES=OFF' \
    '-DLLVM_ENABLE_UNWIND_TABLES=OFF'; do
    grep -Fq -- "$flag" "$BASE"
done

# The accuracy profile and host feature profile change generated tools and must
# invalidate the semantic marker exactly once. Link-pool sizing must never do so.
base_marker="$(marker_block "$BASE")"
grep -Fq 'BOOTSTRAP_SCHEMA=20' <<< "$base_marker"
grep -Fq 'LLVM_ACCURACY_CHECKS=$LLVM_ACCURACY_CHECKS' <<< "$base_marker"
grep -Fq 'LLVM_ENABLE_ASSERTIONS=$llvm_enable_assertions' <<< "$base_marker"
grep -Fq 'LLVM_OPTIMIZED_TABLEGEN=$llvm_optimized_tablegen' <<< "$base_marker"
grep -Fq 'LLVM_ENABLE_PLUGINS=OFF' <<< "$base_marker"
grep -Fq 'LLVM_ENABLE_BACKTRACES=OFF' <<< "$base_marker"
grep -Fq 'LLVM_ENABLE_CRASH_OVERRIDES=OFF' <<< "$base_marker"
grep -Fq 'LLVM_ENABLE_UNWIND_TABLES=OFF' <<< "$base_marker"
if grep -Fq 'LLVM_LINK_JOBS=' <<< "$base_marker"; then
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
core_marker="$(marker_block "$CORE")"
grep -Fq 'LLD_SCHEMA=6' <<< "$core_marker"
grep -Fq 'LLVM_ENABLE_ASSERTIONS=$lld_llvm_enable_assertions' <<< "$core_marker"
grep -Fq 'LLVM_OPTIMIZED_TABLEGEN=$lld_llvm_optimized_tablegen' <<< "$core_marker"
if grep -Fq 'LLVM_LINK_JOBS=' <<< "$core_marker"; then
    printf 'error: link scheduling leaked into the LLD semantic marker\n' >&2
    exit 1
fi

printf 'PowerPC LLVM heavy-hitter policy: verified\n'
