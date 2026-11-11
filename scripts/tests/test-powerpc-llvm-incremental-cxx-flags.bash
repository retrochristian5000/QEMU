#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later

set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
POWERPC="$ROOT/scripts/bootstrap-powerpc-clang.bash"
BASE="$ROOT/scripts/bootstrap-powerpc-clang-base.bash"
CORE="$ROOT/scripts/bootstrap-powerpc-clang-core.bash"
NATIVE="$ROOT/scripts/bootstrap-native-clang.bash"
I386="$ROOT/scripts/bootstrap-i386-clang.bash"

for file in "$POWERPC" "$BASE" "$CORE" "$NATIVE" "$I386"; do
    if [[ ! -f "$file" ]]; then
        printf 'error: required LLVM bootstrap script is missing: %s\n' "$file" >&2
        exit 1
    fi
done

# Native and i386 LLVM already let the active compiler/CMake Release profile
# select its normal host optimization flags. PowerPC must do the same by
# default instead of silently switching the same LLVM source to -O2/-O1.
grep -Fq 'LLVM_CXX_OPTIMIZATION="${POWERPC_LLVM_CXX_OPTIMIZATION:-toolchain-default}"' "$BASE" || {
    printf 'error: PowerPC LLVM does not default to the native Release profile\n' >&2
    exit 1
}
grep -Fq 'toolchain-default|-O0|-O1|-O2|-O3|-Os|-Og)' "$BASE" || {
    printf 'error: PowerPC LLVM no longer accepts the explicit legacy optimization profile\n' >&2
    exit 1
}
grep -Fq 'host_c_release_flags="toolchain-default"' "$BASE"
grep -Fq 'host_cxx_release_flags="toolchain-default"' "$BASE"
grep -Fq '"$LLVM_CXX_OPTIMIZATION" != toolchain-default' "$BASE" || {
    printf 'error: PowerPC LLVM applies custom Release flags without an explicit opt-in\n' >&2
    exit 1
}

grep -Fq 'host_c_release_flags="-O2 -DNDEBUG -fno-function-sections -fno-data-sections"' "$BASE"
grep -Fq 'host_cxx_release_flags="$LLVM_CXX_OPTIMIZATION -DNDEBUG -fno-function-sections -fno-data-sections"' "$BASE"
grep -Fq '"-DCMAKE_C_FLAGS_RELEASE=$host_c_release_flags"' "$BASE"
grep -Fq '"-DCMAKE_CXX_FLAGS_RELEASE=$host_cxx_release_flags"' "$BASE"

for file in "$NATIVE" "$I386"; do
    if grep -Fq 'CMAKE_C_FLAGS_RELEASE=' "$file" ||
       grep -Fq 'CMAKE_CXX_FLAGS_RELEASE=' "$file"; then
        printf 'error: reference LLVM bootstrap has a private Release override: %s\n' \
            "$file" >&2
        exit 1
    fi
done

for file in "$NATIVE" "$I386" "$BASE"; do
    grep -Fq 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' "$file" || {
        printf 'error: standalone LLVM bootstrap inherits ambient QEMU flags: %s\n' "$file" >&2
        exit 1
    }
done
for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
    grep -Eq -- "-u[[:space:]]+$variable([[:space:]]|$)" "$POWERPC" || {
        printf 'error: PowerPC orchestrator does not isolate %s from component bootstraps\n' \
            "$variable" >&2
        exit 1
    }
done

grep -Eq 'BOOTSTRAP_SCHEMA=[0-9]+' "$BASE"
grep -Fq 'HOST_C_RELEASE_FLAGS=$host_c_release_flags' "$BASE"
grep -Fq 'HOST_CXX_RELEASE_FLAGS=$host_cxx_release_flags' "$BASE"
if grep -Fq 'HOST_RELEASE_FLAGS=' "$BASE"; then
    printf 'error: base bootstrap still flattens C and C++ release flags\n' >&2
    exit 1
fi

if grep -Fq 'CMAKE_PARALLEL_JOBS=${JOBS:-native}' "$BASE"; then
    printf 'error: base bootstrap marker still treats JOBS as an artifact input\n' >&2
    exit 1
fi
if grep -Fq 'LLD_CMAKE_PARALLEL_JOBS=${JOBS:-native}' "$CORE"; then
    printf 'error: LLD marker still treats JOBS as an artifact input\n' >&2
    exit 1
fi

grep -Eq 'LLD_SCHEMA=[0-9]+' "$CORE"
grep -Fq 'base_marker_signature="$(cksum "$base_marker" | awk' "$CORE"
grep -Fq 'BASE_MARKER_SIGNATURE=$base_marker_signature' "$CORE"
grep -Fq 'HOST_C_RELEASE_FLAGS=$lld_host_c_release_flags' "$CORE"
grep -Fq 'HOST_CXX_RELEASE_FLAGS=$lld_host_cxx_release_flags' "$CORE"
grep -Fq 'if [[ "$lld_host_c_release_flags" != toolchain-default ]]; then' "$CORE"
grep -Fq 'if [[ "$lld_host_cxx_release_flags" != toolchain-default ]]; then' "$CORE"
if grep -Fq 'BASE_BOOTSTRAP_SIGNATURE=' "$CORE"; then
    printf 'error: LLD marker still keys rebuilds to the raw base script checksum\n' >&2
    exit 1
fi
if grep -Fq 'lld_host_release_flags=' "$CORE"; then
    printf 'error: LLD bootstrap still reuses one release flag string for both languages\n' >&2
    exit 1
fi

printf 'LLVM bootstrap host flag parity: verified\n'
