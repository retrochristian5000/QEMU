#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
BOOTSTRAP="$ROOT/scripts/bootstrap-i386-clang.bash"

fail()
{
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

[[ -f "$BOOTSTRAP" ]] || fail "missing i386 LLVM bootstrap: $BOOTSTRAP"

# The i386-none-elf LLVM build graph is persistent state. Deleting it loses
# CMakeCache.txt, build.ninja, depfiles, and compiled objects, turning an
# interrupted bootstrap or source update into a full restart.
if grep -Fq 'rm -rf "$LLVM_BUILD_DIR"' "$BOOTSTRAP"; then
    fail 'i386 LLVM bootstrap deletes LLVM_BUILD_DIR and destroys incremental state'
fi

grep -Fq 'cmake "${cmake_args[@]}"' "$BOOTSTRAP" ||
    fail 'i386 LLVM bootstrap must reconfigure the existing CMake graph in place'

grep -Fq 'if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then' "$BOOTSTRAP" ||
    fail 'i386 LLVM explicit forced rebuild branch is missing'

grep -Fq 'cmake --build "$LLVM_BUILD_DIR" --target clean "${cmake_parallel_args[@]}"' "$BOOTSTRAP" ||
    fail 'i386 LLVM forced rebuild must clean through the generated backend'

printf 'i386-none-elf LLVM incremental CMake/Ninja contract: verified\n'
