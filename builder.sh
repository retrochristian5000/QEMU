#!/usr/bin/env bash

set -euo pipefail

SOURCE_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
HOST_OS="$(uname -s)"
HOST_ARCH="$(uname -m)"
APPLE_SILICON_HOST=0

if [[ "$HOST_OS" == "Darwin" ]] &&
   [[ "$(sysctl -in hw.optional.arm64 2>/dev/null || printf '0')" == "1" ]]; then
    APPLE_SILICON_HOST=1
fi

if (( APPLE_SILICON_HOST )) &&
   [[ "$HOST_ARCH" != "arm64" && "$HOST_ARCH" != "aarch64" ]]; then
    printf '%s\n' \
        "error: Apple Silicon build is running under Rosetta ($HOST_ARCH)." \
        "rerun it natively with: arch -arm64 ./builder.sh" >&2
    exit 1
fi

if (( APPLE_SILICON_HOST )); then
    DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc-aarch64-apple-darwin"
    DEFAULT_PREFIX="${HOME:-$SOURCE_DIR}/.local/whp-qemu"
else
    DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc"
    DEFAULT_PREFIX="/emulator"
fi

BUILD_DIR="${BUILD_DIR:-$DEFAULT_BUILD_DIR}"
PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
QEMU_TARGET_LIST="${QEMU_TARGET_LIST:-ppc-softmmu}"
ARCH_DEVICE_FILE="${ARCH_DEVICE_FILE:-whp-profile}"
BUILD_TARGETS="${BUILD_TARGETS:-all}"
INSTALL="${INSTALL:-0}"
MACOS_ENABLE_GTK="${MACOS_ENABLE_GTK:-0}"
MACOS_ENABLE_PA="${MACOS_ENABLE_PA:-0}"

for build_path in "$SOURCE_DIR" "$BUILD_DIR"; do
    case "$build_path" in
        *[' ':]*)
            printf 'error: QEMU source and build paths cannot contain spaces or colons\n' >&2
            exit 1
            ;;
    esac
done

export CFLAGS="${CFLAGS:--g0 -pipe -w}"

if (( APPLE_SILICON_HOST )); then
    if ! command -v xcrun >/dev/null 2>&1; then
        printf 'error: xcrun is missing; install the Xcode Command Line Tools\n' >&2
        exit 1
    fi

    export SDKROOT="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    if [[ ! -d "$SDKROOT" ]]; then
        printf 'error: macOS SDK not found at %s\n' "$SDKROOT" >&2
        exit 1
    fi

    if [[ -z "${CC:-}" ]]; then
        export CC="$(xcrun --sdk macosx --find clang)"
    fi
    if [[ -z "${CXX:-}" ]]; then
        export CXX="$(xcrun --sdk macosx --find clang++)"
    fi
    if [[ -z "${OBJC:-}" ]]; then
        export OBJC="$(xcrun --sdk macosx --find clang)"
    fi

    if command -v brew >/dev/null 2>&1; then
        HOMEBREW_PREFIX="$(brew --prefix)"
        if [[ "$HOMEBREW_PREFIX" == "/usr/local" ]]; then
            printf '%s\n' \
                'warning: /usr/local Homebrew may contain Intel libraries.' \
                'Prefer native Apple Silicon Homebrew under /opt/homebrew.' >&2
        fi
        export PATH="$HOMEBREW_PREFIX/bin:$PATH"
        homebrew_pc="$HOMEBREW_PREFIX/lib/pkgconfig:$HOMEBREW_PREFIX/share/pkgconfig"
        export PKG_CONFIG_PATH="$homebrew_pc${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
    fi
fi

# Reuse compiler output when ccache is available, without requiring it.
if command -v ccache >/dev/null 2>&1; then
    if [[ -z "${CC:-}" ]]; then
        export CC="ccache cc"
    elif [[ "$CC" != ccache\ * ]]; then
        export CC="ccache $CC"
    fi
    if [[ -z "${CXX:-}" ]]; then
        export CXX="ccache c++"
    elif [[ "$CXX" != ccache\ * ]]; then
        export CXX="ccache $CXX"
    fi
fi

if command -v nproc >/dev/null 2>&1; then
    DEFAULT_JOBS="$(nproc)"
elif command -v sysctl >/dev/null 2>&1; then
    DEFAULT_JOBS="$(sysctl -n hw.ncpu 2>/dev/null || printf '1')"
else
    DEFAULT_JOBS=1
fi
JOBS="${JOBS:-$DEFAULT_JOBS}"

if [[ -n "${MAKE_CMD:-}" ]]; then
    :
elif command -v gmake >/dev/null 2>&1; then
    MAKE_CMD="gmake"
else
    MAKE_CMD="make"
fi
if ! "$MAKE_CMD" --version 2>/dev/null | head -n 1 | grep -q 'GNU Make'; then
    printf 'error: QEMU requires GNU Make; set MAKE_CMD to a GNU Make binary\n' >&2
    exit 1
fi
export MAKE="$MAKE_CMD"

configure_args=(
    --enable-pixman
    --enable-rng-none
    --enable-slirp
    --enable-tools
    --prefix="$PREFIX"
    --target-list="$QEMU_TARGET_LIST"
    --without-default-devices
    --without-default-features
    --with-devices-ppc="$ARCH_DEVICE_FILE"
)

if (( APPLE_SILICON_HOST )); then
    macos_audio_drivers="coreaudio"
    configure_args+=(
        --enable-cocoa
        --enable-coreaudio
        --objcc="$OBJC"
    )
    if [[ "$MACOS_ENABLE_GTK" == "1" ]]; then
        configure_args+=(--enable-gtk)
    fi
    if [[ "$MACOS_ENABLE_PA" == "1" ]]; then
        configure_args+=(--enable-pa)
        macos_audio_drivers+=",pa"
    fi
    configure_args+=(--audio-drv-list="$macos_audio_drivers")
else
    configure_args+=(
        --enable-gtk
        --enable-pa
    )
fi

# Existing clones cache submodule URLs in .git/config. Keep the OpenBIOS
# checkout mounted from the WHP PPC-Firmware repository before configuring.
if [[ -e "$SOURCE_DIR/.git" ]]; then
    if ! command -v git >/dev/null 2>&1; then
        printf 'error: git is required to mount roms/openbios\n' >&2
        exit 1
    fi
    git -C "$SOURCE_DIR" submodule sync -- roms/openbios
    git -C "$SOURCE_DIR" submodule update --init -- roms/openbios
fi

mkdir -p "$BUILD_DIR"

# Reconfigure only when the host toolchain or requested build settings change.
config_file="$BUILD_DIR/.whp-config"
config_candidate="$config_file.new"
{
    printf 'HOST_OS=%s\n' "$HOST_OS"
    printf 'HOST_ARCH=%s\n' "$HOST_ARCH"
    printf 'CC=%s\n' "${CC:-cc}"
    printf 'CXX=%s\n' "${CXX:-c++}"
    printf 'OBJC=%s\n' "${OBJC:-}"
    printf 'CFLAGS=%s\n' "$CFLAGS"
    printf 'CXXFLAGS=%s\n' "${CXXFLAGS:-}"
    printf 'OBJCFLAGS=%s\n' "${OBJCFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
    printf 'SDKROOT=%s\n' "${SDKROOT:-}"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
    printf 'PKG_CONFIG=%s\n' "${PKG_CONFIG:-pkg-config}"
    printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
    printf 'HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX:-}"
    printf 'MAKE=%s\n' "$MAKE_CMD"
    printf 'NINJA=%s\n' "${NINJA:-}"
    printf 'PYTHON=%s\n' "${PYTHON:-}"
    printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
    printf 'CONFIGURE_ARG=%s\n' "${configure_args[@]}"
} > "$config_candidate"

if [[ ! -f "$BUILD_DIR/build.ninja" ]] ||
   [[ ! -f "$config_file" ]] ||
   ! cmp -s "$config_candidate" "$config_file"; then
    (
        cd "$BUILD_DIR"
        "$SOURCE_DIR/configure" "${configure_args[@]}"
    )
    mv "$config_candidate" "$config_file"
else
    rm -f "$config_candidate"
fi

read -r -a build_target_list <<< "$BUILD_TARGETS"
"$MAKE_CMD" -C "$BUILD_DIR" -j"$JOBS" "${build_target_list[@]}"

# Installation is deliberately separate from compilation so routine rebuilds
# do not recopy the full output tree. Use INSTALL=1 when an install is needed.
if [[ "$INSTALL" == "1" ]]; then
    "$MAKE_CMD" -C "$BUILD_DIR" install
fi
