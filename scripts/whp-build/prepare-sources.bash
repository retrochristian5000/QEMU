# WHP source, toolchain-probe, and firmware preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_sources()
{
# Existing clones cache submodule URLs in .git/config. Keep the OpenBIOS
# checkout mounted from the WHP PPC-Firmware repository before configuring.
if [[ "$BUILD_OPENBIOS" == "1" && -e "$SOURCE_DIR/.git" ]]; then
    if ! command -v git >/dev/null 2>&1; then
        printf 'error: git is required to mount roms/openbios\n' >&2
        exit 1
    fi
    git -C "$SOURCE_DIR" submodule sync -- roms/openbios
    git -C "$SOURCE_DIR" submodule update --init -- roms/openbios
fi

mkdir -p "$BUILD_DIR"

MACOS_COMPILER_MANIFEST="disabled"
MACOS_COMPILER_MANIFEST_SIGNATURE="disabled"
if [[ "$HOST_OS" == "Darwin" && "$MACOS_VERIFY_TOOLCHAIN" == "1" ]]; then
    MACOS_COMPILER_MANIFEST="$BUILD_DIR/.whp-macos-toolchain"
    MACOS_HOST_ARCH="$HOST_ARCH" \
    BUILD_MACHINE_ARCH="$HOST_ARCH" \
    MACOS_COMPILER_MANIFEST="$MACOS_COMPILER_MANIFEST" \
    MACOS_COMPILER_PROBE_DIR="$BUILD_DIR/.whp-macos-toolchain.d" \
    MACOS_ALLOW_NONCLANG="$MACOS_ALLOW_NONCLANG" \
    MACOS_ALLOW_COMPILER_CONFIG="$MACOS_ALLOW_COMPILER_CONFIG" \
    CC="$CC" CXX="$CXX" OBJC="$OBJC" \
    CC_FOR_BUILD="$CC_FOR_BUILD" \
    SDKROOT="$SDKROOT" \
    CFLAGS="${CFLAGS:-}" CXXFLAGS="${CXXFLAGS:-}" \
    OBJCFLAGS="${OBJCFLAGS:-}" CPPFLAGS="${CPPFLAGS:-}" \
    LDFLAGS="${LDFLAGS:-}" \
    MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-}" \
        bash "$SOURCE_DIR/scripts/verify-macos-toolchain.sh"
    MACOS_COMPILER_MANIFEST_SIGNATURE="$(cksum "$MACOS_COMPILER_MANIFEST" |
        awk '{print $1 ":" $2}')"
fi

MACOS_LTO_MANIFEST="disabled"
MACOS_LTO_MANIFEST_SIGNATURE="disabled"
if [[ "$HOST_OS" == "Darwin" && "$QEMU_HOST_LTO" == "1" ]]; then
    MACOS_LTO_MANIFEST="$BUILD_DIR/.whp-macos-lto"
    MACOS_HOST_ARCH="$HOST_ARCH" \
    MACOS_LTO_MANIFEST="$MACOS_LTO_MANIFEST" \
    MACOS_LTO_PROBE_DIR="$BUILD_DIR/.whp-macos-lto.d" \
    CC="$CC" SDKROOT="$SDKROOT" \
    CFLAGS="${CFLAGS:-}" CPPFLAGS="${CPPFLAGS:-}" \
    LDFLAGS="${LDFLAGS:-}" \
    MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-}" \
        bash "$SOURCE_DIR/scripts/verify-macos-lto.sh"
    MACOS_LTO_MANIFEST_SIGNATURE="$(cksum "$MACOS_LTO_MANIFEST" |
        awk '{print $1 ":" $2}')"
fi

OPENBIOS_CONFIG_FILE="$BUILD_DIR/.whp-openbios-meson.env"
if [[ "$BUILD_OPENBIOS" == "1" ]]; then
    BUILD_DIR="$BUILD_DIR" \
    OPENBIOS_DIR="${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}" \
    OPENBIOS_TOOLS_DIR="${OPENBIOS_TOOLS_DIR:-$BUILD_DIR/firmware-tools}" \
    OPENBIOS_CROSS_COMPILE="$OPENBIOS_CROSS_COMPILE" \
    OPENBIOS_FORCE_RECONFIGURE="$OPENBIOS_FORCE_RECONFIGURE" \
    BOOTSTRAP_POWERPC_TOOLCHAIN="$BOOTSTRAP_POWERPC_TOOLCHAIN" \
    POWERPC_TOOLCHAIN_FORCE_REBUILD="$POWERPC_TOOLCHAIN_FORCE_REBUILD" \
    POWERPC_TOOLCHAIN_SOURCE_MODE="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}" \
    POWERPC_TOOLCHAIN_DIR="$POWERPC_TOOLCHAIN_DIR" \
    CC_FOR_BUILD="$CC_FOR_BUILD" \
    CXX_FOR_BUILD="$CXX_FOR_BUILD" \
    STRIP_FOR_BUILD="$STRIP_FOR_BUILD" \
    PKG_CONFIG_FOR_BUILD="$PKG_CONFIG_FOR_BUILD" \
    MAKE_CMD="$MAKE_CMD" \
    JOBS="$JOBS" \
        bash "$SOURCE_DIR/scripts/whp-build/configure-openbios.bash"
else
    rm -f "$OPENBIOS_CONFIG_FILE"
fi
}
