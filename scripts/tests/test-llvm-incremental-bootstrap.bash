#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

fail()
{
    printf 'FAIL: %s\n' "$*" >&2
    exit 1
}

if [[ $# -ne 2 ]]; then
    fail "usage: $0 <bootstrap-relative-path> <label>"
fi

BOOTSTRAP="$ROOT/$1"
LABEL="$2"

[[ -f "$BOOTSTRAP" ]] || fail "missing $LABEL bootstrap: $BOOTSTRAP"

require_fixed()
{
    local needle="$1"
    local message="$2"

    grep -Fq -- "$needle" "$BOOTSTRAP" || fail "$LABEL: $message"
}

# LLVM's generated CMake/Ninja tree is persistent state. Removing it loses
# CMakeCache.txt, build.ninja, depfiles, and compiled objects, turning an
# interrupted bootstrap or source update into a full restart.
if grep -Fq -- 'rm -rf "$LLVM_BUILD_DIR"' "$BOOTSTRAP"; then
    fail "$LABEL bootstrap deletes LLVM_BUILD_DIR and destroys incremental state"
fi

# The native LLVM compiler uses an admitted CMake seed rather than an
# ambient executable named "cmake". Other LLVM bootstrap lanes retain their
# existing CMake command. Match the real provider in both configure and clean.
case "$1" in
    scripts/bootstrap-native-clang.bash) cmake_command='"$cmake_cmd"' ;;
    *) cmake_command=cmake ;;
esac
require_fixed "$cmake_command \"${cmake_args[@]}\"" \
    'bootstrap must reconfigure the existing CMake graph in place'
require_fixed 'if [[ "$TOOLCHAIN_FORCE_REBUILD" == 1 ]]; then' \
    'explicit forced rebuild branch is missing'
require_fixed "$cmake_command --build \"\$LLVM_BUILD_DIR\" --target clean \"${cmake_parallel_args[@]}\"" \
    'forced rebuild must clean through the generated backend'

printf '%s incremental CMake/Ninja contract: verified\n' "$LABEL"
