#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/../.." && pwd)"
: "${BUILD_DIR:?BUILD_DIR is required}"

mkdir -p "$BUILD_DIR"
build_root="$(cd -- "$BUILD_DIR" && pwd)"
config="$build_root/.whp-openbios-meson.env"
temporary="$config.new.$$"
source_mode="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
compiler_mode="${POWERPC_TOOLCHAIN_COMPILER:-}"
if [[ -z "$compiler_mode" ]]; then
    case "$(uname -s)" in
        Darwin) compiler_mode=clang ;;
        *) compiler_mode=gcc ;;
    esac
fi
tools_dir="${OPENBIOS_TOOLS_DIR:-$build_root/firmware-tools}"
openbios_build_dir="${OPENBIOS_BUILD_DIR:-$build_root/firmware/openbios}"
hostcc="${OPENBIOS_HOSTCC:-${CC_FOR_BUILD:-${CC:-cc}}}"
hostcxx="${OPENBIOS_HOSTCXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
hoststrip="${OPENBIOS_HOSTSTRIP:-${STRIP_FOR_BUILD:-strip}}"
make_cmd="${MAKE_CMD:-${MAKE:-make}}"
jobs="${JOBS:-}"

cleanup()
{
    rm -f "$temporary"
}
trap cleanup EXIT

case "$source_mode" in
    release|git) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_SOURCE_MODE must be release or git\n' >&2
        exit 1
        ;;
esac
case "$compiler_mode" in
    clang|gcc) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_COMPILER must be clang or gcc\n' >&2
        exit 1
        ;;
esac
if [[ "$compiler_mode" == clang && "$source_mode" != release ]]; then
    printf '%s\n' \
        'error: the PowerPC Clang lane currently retains release binutils.' \
        'set POWERPC_TOOLCHAIN_SOURCE_MODE=release or unset it.' >&2
    exit 1
fi

mkdir -p "$openbios_build_dir"
openbios_build_dir="$(cd -- "$openbios_build_dir" && pwd)"
case "$openbios_build_dir/" in
    "$build_root/"*) ;;
    *)
        printf '%s\n' \
            'error: OPENBIOS_BUILD_DIR must be inside the QEMU build directory.' \
            "QEMU build:     $build_root" \
            "OpenBIOS build: $openbios_build_dir" >&2
        exit 1
        ;;
esac
if [[ "$openbios_build_dir" == "$build_root" ]]; then
    printf '%s\n' \
        'error: OPENBIOS_BUILD_DIR cannot be the QEMU build root itself.' \
        "QEMU build: $build_root" >&2
    exit 1
fi

if [[ -z "$jobs" ]]; then
    if command -v nproc >/dev/null 2>&1; then
        jobs="$(nproc)"
    elif command -v sysctl >/dev/null 2>&1; then
        jobs="$(sysctl -n hw.ncpu 2>/dev/null || printf '1')"
    else
        jobs=1
    fi
fi

umask 077
{
    printf 'OPENBIOS_DIR=%q\n' "${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}"
    printf 'OPENBIOS_BUILD_DIR=%q\n' "$openbios_build_dir"
    printf 'OPENBIOS_TOOLS_DIR=%q\n' "$tools_dir"
    printf 'OPENBIOS_HOSTCC=%q\n' "$hostcc"
    printf 'OPENBIOS_HOSTCXX=%q\n' "$hostcxx"
    printf 'OPENBIOS_HOSTSTRIP=%q\n' "$hoststrip"
    printf 'OPENBIOS_TOKE=%q\n' "${OPENBIOS_TOKE:-}"
    printf 'OPENBIOS_CROSS_COMPILE=%q\n' "${OPENBIOS_CROSS_COMPILE:-}"
    printf 'OPENBIOS_FORCE_RECONFIGURE=%q\n' "${OPENBIOS_FORCE_RECONFIGURE:-0}"
    printf 'BOOTSTRAP_POWERPC_TOOLCHAIN=%q\n' "${BOOTSTRAP_POWERPC_TOOLCHAIN:-1}"
    printf 'POWERPC_TOOLCHAIN_FORCE_REBUILD=%q\n' "${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
    printf 'POWERPC_TOOLCHAIN_SOURCE_MODE=%q\n' "$source_mode"
    printf 'POWERPC_TOOLCHAIN_COMPILER=%q\n' "$compiler_mode"
    printf 'POWERPC_TOOLCHAIN_DIR=%q\n' \
        "${POWERPC_TOOLCHAIN_DIR:-$tools_dir/powerpc-elf}"
    printf 'POWERPC_TOOLCHAIN_WORK_DIR=%q\n' \
        "${POWERPC_TOOLCHAIN_WORK_DIR:-$tools_dir/toolchain-work/powerpc-elf}"
    printf 'POWERPC_TOOLCHAIN_DOWNLOAD_DIR=%q\n' \
        "${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$tools_dir/toolchain-downloads}"
    printf 'POWERPC_TOOLCHAIN_GIT_OFFLINE=%q\n' \
        "${POWERPC_TOOLCHAIN_GIT_OFFLINE:-0}"
    printf 'POWERPC_BINUTILS_GIT_URL=%q\n' \
        "${POWERPC_BINUTILS_GIT_URL:-https://sourceware.org/git/binutils-gdb.git}"
    printf 'POWERPC_BINUTILS_GIT_REF=%q\n' \
        "${POWERPC_BINUTILS_GIT_REF:-binutils-2_46-branch}"
    printf 'POWERPC_BINUTILS_GIT_COMMIT=%q\n' \
        "${POWERPC_BINUTILS_GIT_COMMIT:-}"
    printf 'POWERPC_GCC_GIT_URL=%q\n' \
        "${POWERPC_GCC_GIT_URL:-https://gcc.gnu.org/git/gcc.git}"
    printf 'POWERPC_GCC_GIT_REF=%q\n' \
        "${POWERPC_GCC_GIT_REF:-releases/gcc-16}"
    printf 'POWERPC_GCC_GIT_COMMIT=%q\n' \
        "${POWERPC_GCC_GIT_COMMIT:-}"
    printf 'POWERPC_LLVM_GIT_URL=%q\n' \
        "${POWERPC_LLVM_GIT_URL:-https://github.com/retrochristian5000/LLVM.git}"
    printf 'POWERPC_LLVM_GIT_REF=%q\n' \
        "${POWERPC_LLVM_GIT_REF:-main}"
    printf 'POWERPC_LLVM_GIT_COMMIT=%q\n' \
        "${POWERPC_LLVM_GIT_COMMIT:-e7dd336e0f7884c34108a1e722205a16c3f5307b}"
    printf 'POWERPC_LLVM_GIT_OFFLINE=%q\n' \
        "${POWERPC_LLVM_GIT_OFFLINE:-0}"
    printf 'CONFIG_SHELL=%q\n' "${CONFIG_SHELL:-${WHP_BUILD_BASH:-/bin/bash}}"
    printf 'PKG_CONFIG_FOR_BUILD=%q\n' \
        "${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"
    printf 'MAKE_CMD=%q\n' "$make_cmd"
    printf 'JOBS=%q\n' "$jobs"
} > "$temporary"
mv -f "$temporary" "$config"
trap - EXIT
