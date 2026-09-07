#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$ROOT/scripts/bootstrap-native-clang.bash"

fail()
{
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ -f "$BOOTSTRAP" ]] || fail "missing native LLVM bootstrap: $BOOTSTRAP"

# Incremental native LLVM builds must preserve CMake/Ninja's binary tree.
# Deleting LLVM_BUILD_DIR discards CMakeCache.txt, build.ninja, depfiles and
# all compiled objects, so an interrupted or source-updated bootstrap restarts
# from zero instead of letting CMake reconfigure and Ninja rebuild only what
# changed.
if grep -Fq 'rm -rf "$LLVM_BUILD_DIR"' "$BOOTSTRAP"; then
    fail 'native LLVM bootstrap deletes LLVM_BUILD_DIR and destroys incremental state'
fi

grep -Fq 'cmake "${cmake_args[@]}"' "$BOOTSTRAP" ||
    fail 'native LLVM bootstrap must reconfigure the existing CMake build tree in place'

grep -Fq 'if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then' "$BOOTSTRAP" ||
    fail 'native LLVM forced rebuild branch is missing'

grep -Fq 'cmake --build "$LLVM_BUILD_DIR" --target clean "${cmake_parallel_args[@]}"' "$BOOTSTRAP" ||
    fail 'native LLVM forced rebuild must clean through the generated backend'

printf 'Native LLVM incremental CMake/Ninja contract: verified\n'
