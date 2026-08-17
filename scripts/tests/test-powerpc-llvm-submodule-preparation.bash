#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SOURCE_DIR="$ROOT"
PREPARE_SOURCES="$ROOT/scripts/whp-build/prepare-sources.bash"
CONFIGURE_OPENBIOS="$ROOT/scripts/whp-build/configure-openbios.bash"
CLANG_BOOTSTRAP="$ROOT/scripts/bootstrap-powerpc-clang-base.sh"
REAL_BASH="$(command -v bash)"
tmpdir="$(mktemp -d)"
trap 'rm -rf "$tmpdir"' EXIT

git_log="$tmpdir/git.log"
bash_log="$tmpdir/bash.log"

# Exercise the source-preparation function without touching the checkout.
# The git shim records which submodules the stage owns; the bash shim records
# the compiler lane propagated across the configure-openbios subprocess boundary.
git()
{
    printf '%s\n' "$*" >> "$git_log"
}

bash()
{
    printf 'compiler=%s command=%s\n' \
        "${POWERPC_TOOLCHAIN_COMPILER:-unset}" "$*" >> "$bash_log"
}

source "$PREPARE_SOURCES"

BUILD_OPENBIOS=1
BUILD_DIR="$tmpdir/build"
MACOS_VERIFY_TOOLCHAIN=0
QEMU_HOST_LTO=0
OPENBIOS_CROSS_COMPILE=""
OPENBIOS_FORCE_RECONFIGURE=0
BOOTSTRAP_POWERPC_TOOLCHAIN=1
POWERPC_TOOLCHAIN_FORCE_REBUILD=0
POWERPC_TOOLCHAIN_SOURCE_MODE=release
POWERPC_TOOLCHAIN_DIR="$tmpdir/toolchain"
CC_FOR_BUILD=cc
CXX_FOR_BUILD=c++
STRIP_FOR_BUILD=strip
PKG_CONFIG_FOR_BUILD=pkg-config
MAKE_CMD=make
JOBS=1

run_default_clang_case()
{
    : > "$git_log"
    : > "$bash_log"
    HOST_OS=Linux
    unset POWERPC_TOOLCHAIN_COMPILER

    whp_prepare_sources

    grep -Fx -- "-C $ROOT submodule sync -- roms/openbios toolchains/llvm-project" \
        "$git_log"
    grep -Fx -- "-C $ROOT submodule update --init -- roms/openbios toolchains/llvm-project" \
        "$git_log"
    grep -Fq 'compiler=clang ' "$bash_log"
}

run_explicit_gcc_case()
{
    : > "$git_log"
    : > "$bash_log"
    HOST_OS=Darwin
    POWERPC_TOOLCHAIN_COMPILER=gcc

    whp_prepare_sources

    grep -Fx -- "-C $ROOT submodule sync -- roms/openbios" "$git_log"
    grep -Fx -- "-C $ROOT submodule update --init -- roms/openbios" "$git_log"
    if grep -Fq 'toolchains/llvm-project' "$git_log"; then
        printf 'error: GCC OpenBIOS lane initialized the LLVM toolchain submodule\n' >&2
        exit 1
    fi
    grep -Fq 'compiler=gcc ' "$bash_log"
}

run_default_clang_case
run_explicit_gcc_case

clang_config_dir="$tmpdir/clang-config"
BUILD_DIR="$clang_config_dir" POWERPC_TOOLCHAIN_COMPILER=clang \
    "$REAL_BASH" "$CONFIGURE_OPENBIOS"
clang_config="$clang_config_dir/.whp-openbios-meson.env"
grep -Fxq 'POWERPC_TOOLCHAIN_COMPILER=clang' "$clang_config"
grep -Fq 'POWERPC_LLVM_SUBMODULE_PATH=' "$clang_config"
if grep -Eq '^POWERPC_(BINUTILS|GCC|TOOLCHAIN_GIT_)' "$clang_config"; then
    printf 'error: Clang configuration still exports GNU source settings\n' >&2
    exit 1
fi

gcc_config_dir="$tmpdir/gcc-config"
BUILD_DIR="$gcc_config_dir" POWERPC_TOOLCHAIN_COMPILER=gcc \
    "$REAL_BASH" "$CONFIGURE_OPENBIOS"
gcc_config="$gcc_config_dir/.whp-openbios-meson.env"
grep -Fxq 'POWERPC_TOOLCHAIN_COMPILER=gcc' "$gcc_config"
grep -Fq 'POWERPC_BINUTILS_GIT_URL=' "$gcc_config"
grep -Fq 'POWERPC_GCC_GIT_URL=' "$gcc_config"
if grep -Fq 'POWERPC_LLVM_' "$gcc_config"; then
    printf 'error: explicit GCC configuration still exports LLVM settings\n' >&2
    exit 1
fi

# The LLVM compiler bootstrap must preserve CMake/Ninja state between pinned
# revisions. Distribution targets keep the install focused while retaining the
# LLVM headers, libraries, and CMake package needed by the later LLD/Meson lanes.
if grep -Fq 'rm -rf "$LLVM_BUILD_DIR"' "$CLANG_BOOTSTRAP"; then
    printf 'error: LLVM bootstrap still destroys its CMake build directory\n' >&2
    exit 1
fi
grep -Fq 'BOOTSTRAP_SCHEMA=14' "$CLANG_BOOTSTRAP"
grep -Fq 'LLVM_CMAKE_MODE=incremental-distribution-fast-host-flags' "$CLANG_BOOTSTRAP"
grep -Fq -- '-DLLVM_DISTRIBUTION_COMPONENTS=' "$CLANG_BOOTSTRAP"
grep -Fq -- 'cmake --build "$LLVM_BUILD_DIR" --target distribution' "$CLANG_BOOTSTRAP"
grep -Fq -- 'cmake --build "$LLVM_BUILD_DIR" --target install-distribution' "$CLANG_BOOTSTRAP"
grep -Fq -- 'llvm-headers;llvm-libraries;cmake-exports' "$CLANG_BOOTSTRAP"
for cmake_flag in \
    '-DLLVM_INCLUDE_DOCS=OFF' \
    '-DLLVM_INCLUDE_UTILS=OFF' \
    '-DLLVM_INCLUDE_RUNTIMES=OFF' \
    '-DLLVM_ENABLE_BINDINGS=OFF' \
    '-DLLVM_ENABLE_WARNINGS=OFF' \
    '-DLLVM_ENABLE_PEDANTIC=OFF'; do
    grep -Fq -- "$cmake_flag" "$CLANG_BOOTSTRAP"
done
grep -Fq -- '-DCMAKE_C_FLAGS_RELEASE=-O2 -DNDEBUG' "$CLANG_BOOTSTRAP"
grep -Fq -- '-DCMAKE_CXX_FLAGS_RELEASE=-O2 -DNDEBUG' "$CLANG_BOOTSTRAP"

printf 'PowerPC LLVM submodule preparation: verified\n'
