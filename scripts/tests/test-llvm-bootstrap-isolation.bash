#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
native="$ROOT/scripts/bootstrap-native-clang.sh"
i386="$ROOT/scripts/bootstrap-i386-clang.sh"
powerpc="$ROOT/scripts/bootstrap-powerpc-clang.sh"

for script in "$native" "$i386" "$powerpc"; do
    [[ -f "$script" ]] || {
        printf 'error: missing LLVM bootstrap: %s\n' "$script" >&2
        exit 1
    }
done

# Native LLVM is invoked by build.sh before the normal QEMU host-flag cleanup,
# and the i386 bootstrap is invoked directly by the SeaBIOS preparation path.
# Both therefore own a local boundary against ambient host-object flags.
for script in "$native" "$i386"; do
    grep -Fq 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' "$script" || {
        printf 'error: LLVM bootstrap inherits QEMU host flags: %s\n' "$script" >&2
        exit 1
    }
done

# PowerPC already enters its compiler stages through a dedicated clean env.
# Keep that single boundary instead of duplicating ad-hoc unsets in the base.
for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
    grep -Fq -- "-u $variable" "$powerpc" || {
        printf 'error: PowerPC LLVM clean environment retains %s\n' "$variable" >&2
        exit 1
    }
done

# Exercise the exact frontend -> IR verifier path implicated by the regression:
# keeping non-leaf frame pointers while omitting leaf frame pointers emits the
# modern "non-leaf-no-reserve" function attribute.
grep -Fq '"$prefix/bin/clang" -fno-omit-frame-pointer -momit-leaf-frame-pointer \' "$native" || {
    printf 'error: native LLVM cache check does not exercise non-leaf frame-pointer IR\n' >&2
    exit 1
}

# A PowerPC compiler graph may be incremental within one LLVM revision, but it
# must not be reused after the gitlink changes. Key the build directory to the
# exact source revision selected by the QEMU tree.
grep -Fq 'POWERPC_LLVM_BUILD_DIR="$TOOLCHAIN_WORK_DIR/llvm-build/$llvm_revision"' "$powerpc" || {
    printf 'error: PowerPC LLVM build graph is not revision-isolated\n' >&2
    exit 1
}

printf 'LLVM bootstrap environment isolation: verified\n'
