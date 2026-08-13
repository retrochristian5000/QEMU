#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
PREPARE_SOURCES="$ROOT/scripts/whp-build/prepare-sources.bash"
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
    HOST_OS=Darwin
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

printf 'PowerPC LLVM submodule preparation: verified\n'
