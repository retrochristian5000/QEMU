#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
ORCHESTRATOR="$ROOT/scripts/bootstrap-powerpc-clang.sh"
CORE="$ROOT/scripts/bootstrap-powerpc-clang-core.sh"
BASE="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"

for file in "$ORCHESTRATOR" "$CORE" "$BASE"; do
    [[ -f "$file" ]] || {
        printf 'error: required LLVM bootstrap script is missing: %s\n' "$file" >&2
        exit 1
    }
done

# A bootstrap script checksum is not permission to erase the LLVM object graph.
# Semantic markers decide whether the base must be revisited; only an explicit
# POWERPC_TOOLCHAIN_FORCE_REBUILD=1 may request Ninja's clean target.
for file in "$ORCHESTRATOR" "$CORE"; do
    if grep -Fq 'base_force=1' "$file"; then
        printf 'error: %s promotes bootstrap checksum drift to a clean LLVM rebuild\n' "$file" >&2
        exit 1
    fi
    if grep -Fq 'POWERPC_TOOLCHAIN_FORCE_REBUILD="$base_force"' "$file"; then
        printf 'error: %s still passes derived clean-rebuild state into the LLVM base\n' "$file" >&2
        exit 1
    fi
done

# LLD already keys itself to the completed base marker. A raw script checksum
# duplicates that identity and rebuilds LLD for comments/refactors that do not
# change the produced compiler.
if grep -Fq 'BASE_BOOTSTRAP_SIGNATURE=$base_signature' "$CORE"; then
    printf 'error: LLD marker still treats the whole base script as an artifact input\n' >&2
    exit 1
fi
grep -Fq 'BASE_MARKER_SIGNATURE=$base_marker_signature' "$CORE"

# Preserve the deliberate escape hatch: explicit force-rebuild is the only
# normal path that should clean the persistent LLVM Ninja tree.
grep -Fq 'if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then' "$BASE"
grep -Fq 'cmake --build "$LLVM_BUILD_DIR" --target clean' "$BASE"

printf 'PowerPC LLVM clean-rebuild policy: verified\n'
