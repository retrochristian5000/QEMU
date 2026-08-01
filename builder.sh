#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
BUILD_DIR="${BUILD_DIR:-$SOURCE_DIR/build/whp-ppc}"
PREFIX="${PREFIX:-/emulator}"
QEMU_TARGET_LIST="${QEMU_TARGET_LIST:-ppc-softmmu}"
ARCH_DEVICE_FILE="${ARCH_DEVICE_FILE:-whp-profile}"
BUILD_TARGETS="${BUILD_TARGETS:-all}"
INSTALL="${INSTALL:-0}"

export CFLAGS="${CFLAGS:--g0 -pipe -w}"

# Reuse compiler output when ccache is available, without requiring it.
if [[ -z "${CC:-}" ]] && command -v ccache >/dev/null 2>&1; then
    export CC="ccache cc"
fi
if [[ -z "${CXX:-}" ]] && command -v ccache >/dev/null 2>&1; then
    export CXX="ccache c++"
fi

if command -v nproc >/dev/null 2>&1; then
    DEFAULT_JOBS="$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
    DEFAULT_JOBS="$(sysctl -n hw.ncpu 2>/dev/null || printf '1')"
else
    DEFAULT_JOBS=1
fi
JOBS="${JOBS:-$DEFAULT_JOBS}"

configure_args=(
    --enable-gtk
    --enable-pixman
    --enable-pa
    --enable-rng-none
    --enable-slirp
    --enable-tools
    --prefix="$PREFIX"
    --target-list="$QEMU_TARGET_LIST"
    --without-default-devices
    --without-default-features
    --with-devices-ppc="$ARCH_DEVICE_FILE"
)

mkdir -p "$BUILD_DIR"

# Reconfigure only when the requested build settings change. This keeps Meson
# and Ninja's incremental state intact across normal emulator rebuilds.
config_signature="$({
    printf 'CC=%s\n' "${CC:-cc}"
    printf 'CXX=%s\n' "${CXX:-c++}"
    printf 'CFLAGS=%s\n' "$CFLAGS"
    printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
    printf 'CONFIGURE_ARG=%s\n' "${configure_args[@]}"
} | sha256sum | awk '{print $1}')"
signature_file="$BUILD_DIR/.whp-config-signature"

if [[ ! -f "$BUILD_DIR/build.ninja" ]] ||
   [[ ! -f "$signature_file" ]] ||
   [[ "$(<"$signature_file")" != "$config_signature" ]]; then
    (
        cd "$BUILD_DIR"
        "$SOURCE_DIR/configure" "${configure_args[@]}"
    )
    printf '%s\n' "$config_signature" > "$signature_file"
fi

read -r -a build_target_list <<< "$BUILD_TARGETS"
make -C "$BUILD_DIR" -j"$JOBS" "${build_target_list[@]}"

# Installation is deliberately separate from compilation so routine rebuilds
# do not recopy the full output tree. Use INSTALL=1 when an install is needed.
if [[ "$INSTALL" == 1 ]]; then
    make -C "$BUILD_DIR" install
fi
