#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"

bootstraps=(
    "$ROOT/scripts/bootstrap-native-clang.sh"
    "$ROOT/scripts/bootstrap-i386-clang.sh"
    "$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
)

for script in "${bootstraps[@]}"; do
    [[ -f "$script" ]] || {
        printf 'error: missing LLVM bootstrap: %s\n' "$script" >&2
        exit 1
    }

    # LLVM bootstraps are tool builds, not QEMU host-object builds.  Ambient
    # optimization/sanitizer/frame-pointer/linker flags must not cross this
    # boundary; CMake receives the bootstrap's explicit ABI policy instead.
    grep -Fq 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' "$script" || {
        printf 'error: LLVM bootstrap inherits QEMU host flags: %s\n' "$script" >&2
        exit 1
    }
done

native="$ROOT/scripts/bootstrap-native-clang.sh"
powerpc="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"

# Exercise the exact frontend -> IR verifier path implicated by the regression.
grep -Fq '"$prefix/bin/clang" -fno-omit-frame-pointer -x c -c - -o /dev/null' "$native" || {
    printf 'error: native LLVM cache check does not exercise frame-pointer IR\n' >&2
    exit 1
}

# Never retain a PowerPC LLVM CMake/Ninja graph across a toolchain rebuild.
# The source tree may gain new IR attributes before old objects are relinked.
grep -Fq 'rm -rf "$LLVM_BUILD_DIR"' "$powerpc" || {
    printf 'error: PowerPC LLVM bootstrap can reuse a stale object graph\n' >&2
    exit 1
}

printf 'LLVM bootstrap environment isolation: verified\n'
