# WHP configuration identity and configure execution stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_configure_build()
{
# Reconfigure only when the build machine, host toolchain, SDK, dependencies,
# firmware toolchain, requested QEMU settings, or portable device policy change.
WHP_PPC_DEVICE_CONFIG_SIGNATURE=disabled
case ",$QEMU_TARGET_LIST," in
    *,ppc-softmmu,*)
        WHP_PPC_DEVICE_CONFIG="$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
        if [[ ! -f "$WHP_PPC_DEVICE_CONFIG" ]]; then
            printf 'error: missing generated PPC device configuration: %s\n' \
                "$WHP_PPC_DEVICE_CONFIG" >&2
            exit 1
        fi
        configure_args+=(--with-devices-ppc=whp-user)
        WHP_PPC_DEVICE_CONFIG_SIGNATURE="$(cksum "$WHP_PPC_DEVICE_CONFIG" |
            awk '{print $1 ":" $2}')"
        ;;
esac

config_file="$BUILD_DIR/.whp-config"
config_candidate="$config_file.new"
{
    printf 'HOST_OS=%s\n' "$HOST_OS"
    printf 'PROCESS_ARCH=%s\n' "$PROCESS_ARCH"
    printf 'PHYSICAL_ARCH=%s\n' "$PHYSICAL_ARCH"
    printf 'HOST_ARCH=%s\n' "$HOST_ARCH"
    printf 'ROSETTA_TRANSLATED=%s\n' "$ROSETTA_TRANSLATED"
    printf 'MACOS_ALLOW_ROSETTA=%s\n' "$MACOS_ALLOW_ROSETTA"
    printf 'MACOS_VERIFY_TOOLCHAIN=%s\n' "$MACOS_VERIFY_TOOLCHAIN"
    printf 'MACOS_ALLOW_NONCLANG=%s\n' "$MACOS_ALLOW_NONCLANG"
    printf 'MACOS_ALLOW_COMPILER_CONFIG=%s\n' "$MACOS_ALLOW_COMPILER_CONFIG"
    printf 'MACOS_COMPILER_MANIFEST=%s\n' "$MACOS_COMPILER_MANIFEST"
    printf 'MACOS_COMPILER_MANIFEST_SIGNATURE=%s\n' "$MACOS_COMPILER_MANIFEST_SIGNATURE"
    printf 'MACOS_LTO_MANIFEST=%s\n' "$MACOS_LTO_MANIFEST"
    printf 'MACOS_LTO_MANIFEST_SIGNATURE=%s\n' "$MACOS_LTO_MANIFEST_SIGNATURE"
    printf 'CC_FOR_BUILD=%s\n' "$CC_FOR_BUILD"
    printf 'CXX_FOR_BUILD=%s\n' "$CXX_FOR_BUILD"
    printf 'OBJC_FOR_BUILD=%s\n' "$OBJC_FOR_BUILD"
    printf 'STRIP_FOR_BUILD=%s\n' "$STRIP_FOR_BUILD"
    printf 'PKG_CONFIG_FOR_BUILD=%s\n' "$PKG_CONFIG_FOR_BUILD"
    printf 'CC=%s\n' "${CC:-cc}"
    printf 'CXX=%s\n' "${CXX:-c++}"
    printf 'OBJC=%s\n' "${OBJC:-}"
    printf 'CFLAGS=%s\n' "$CFLAGS"
    printf 'CXXFLAGS=%s\n' "${CXXFLAGS:-}"
    printf 'OBJCFLAGS=%s\n' "${OBJCFLAGS:-}"
    printf 'CPPFLAGS=%s\n' "${CPPFLAGS:-}"
    printf 'LDFLAGS=%s\n' "${LDFLAGS:-}"
    printf 'DEVELOPER_DIR=%s\n' "${DEVELOPER_DIR:-}"
    printf 'SDKROOT=%s\n' "${SDKROOT:-}"
    printf 'MACOS_SDK_VERSION=%s\n' "${MACOS_SDK_VERSION:-}"
    printf 'MACOSX_DEPLOYMENT_TARGET=%s\n' "${MACOSX_DEPLOYMENT_TARGET:-}"
    printf 'PKG_CONFIG=%s\n' "${PKG_CONFIG:-pkg-config}"
    printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
    printf 'PKG_CONFIG_PATH_FOR_BUILD=%s\n' "${PKG_CONFIG_PATH_FOR_BUILD:-}"
    printf 'HOMEBREW_PREFIX=%s\n' "${HOMEBREW_PREFIX:-}"
    printf 'MAKE=%s\n' "$MAKE_CMD"
    printf 'NINJA=%s\n' "${NINJA:-}"
    printf 'PYTHON=%s\n' "${PYTHON:-}"
    printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
    printf 'QEMU_HOST_LTO=%s\n' "$QEMU_HOST_LTO"
    printf 'BUILD_OPENBIOS=%s\n' "$BUILD_OPENBIOS"
    printf 'OPENBIOS_CROSS_COMPILE=%s\n' "$OPENBIOS_CROSS_COMPILE"
    printf 'BOOTSTRAP_POWERPC_TOOLCHAIN=%s\n' "$BOOTSTRAP_POWERPC_TOOLCHAIN"
    printf 'POWERPC_TOOLCHAIN_DIR=%s\n' "$POWERPC_TOOLCHAIN_DIR"
    printf 'WHP_PPC_DEVICE_CONFIG_SIGNATURE=%s\n' "$WHP_PPC_DEVICE_CONFIG_SIGNATURE"
    printf 'CONFIGURE_ARG=%s\n' "${configure_args[*]}"
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
}
