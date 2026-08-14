# WHP host, toolchain, and build-policy preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

compiler_has_cache_wrapper()
{
    local token base
    local cache_command=()

    read -r -a cache_command <<< "$1"
    for token in "${cache_command[@]}"; do
        base="$(basename "$token")"
        case "$base" in
            ccache|sccache|distcc|icecc) return 0 ;;
        esac
    done
    return 1
}

flag_string_has_lto()
{
    local value="$1"
    local token
    local tokens=()

    read -r -a tokens <<< "$value"
    for token in "${tokens[@]}"; do
        case "$token" in
            -flto|-flto=*|-fno-lto|-Wl,*lto*|-Wl,*LTO*|\
            -object_path_lto*|-lto_library*|-cache_path_lto*|\
            -Xlinker=*lto*|-Xlinker=*LTO*) return 0 ;;
        esac
    done
    return 1
}

reject_global_lto_flags()
{
    local variable value

    for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        if [[ -n "$value" ]] && flag_string_has_lto "$value"; then
            printf '%s\n' \
                "error: $variable contains an LTO option: $value" \
                'LTO must be selected with QEMU_HOST_LTO so it remains inside' \
                "QEMU's Meson host build and cannot leak into firmware or" \
                'build-machine toolchains.' >&2
            exit 1
        fi
    done
}

whp_prepare_host_identity()
{
    HOST_OS="$(uname -s)"
    PROCESS_ARCH="$(uname -m)"
    HOST_ARCH="$PROCESS_ARCH"
    PHYSICAL_ARCH="$PROCESS_ARCH"
    ROSETTA_TRANSLATED=0
    APPLE_SILICON_HOST=0
    APPLE_SILICON_NATIVE=0

    if [[ "$HOST_OS" == Darwin ]]; then
        if [[ "$(sysctl -in hw.optional.arm64 2>/dev/null || printf '0')" == 1 ]]; then
            PHYSICAL_ARCH=arm64
            APPLE_SILICON_HOST=1
        fi
        if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')" == 1 ]]; then
            ROSETTA_TRANSLATED=1
        fi

        HOST_ARCH="$(whp_canonical_macos_arch "$PROCESS_ARCH")" || {
            printf 'error: unsupported macOS process architecture: %s\n' \
                "$PROCESS_ARCH" >&2
            exit 1
        }
        PHYSICAL_ARCH="$(whp_canonical_macos_arch "$PHYSICAL_ARCH")" || {
            printf 'error: unsupported macOS physical architecture: %s\n' \
                "$PHYSICAL_ARCH" >&2
            exit 1
        }
        if [[ "$PHYSICAL_ARCH" == arm64 && "$HOST_ARCH" == arm64 ]]; then
            APPLE_SILICON_NATIVE=1
        fi
    fi

    MACOS_ALLOW_ROSETTA="${MACOS_ALLOW_ROSETTA:-0}"
    MACOS_ALLOW_MIXED_HOMEBREW="${MACOS_ALLOW_MIXED_HOMEBREW:-0}"
    MACOS_ARCH_FLAGS="${MACOS_ARCH_FLAGS:-1}"
    MACOS_VERIFY_TOOLCHAIN="${MACOS_VERIFY_TOOLCHAIN:-1}"
    MACOS_ALLOW_NONCLANG="${MACOS_ALLOW_NONCLANG:-0}"
    MACOS_ALLOW_COMPILER_CONFIG="${MACOS_ALLOW_COMPILER_CONFIG:-0}"

    whp_require_boolean_values \
        MACOS_ALLOW_ROSETTA MACOS_ALLOW_MIXED_HOMEBREW MACOS_ARCH_FLAGS \
        MACOS_VERIFY_TOOLCHAIN MACOS_ALLOW_NONCLANG MACOS_ALLOW_COMPILER_CONFIG || exit 1

    if [[ "$HOST_OS" == Darwin && "$ROSETTA_TRANSLATED" == 1 &&
          "$MACOS_ALLOW_ROSETTA" != 1 ]]; then
        printf '%s\n' \
            'error: the build is running under Rosetta translation.' \
            'rerun natively with: arch -arm64 ./build.sh' \
            'or explicitly allow an x86_64 build with:' \
            '  MACOS_ALLOW_ROSETTA=1 ./build.sh' >&2
        exit 1
    fi
}

whp_prepare_build_defaults()
{
    if [[ "$HOST_OS" == Darwin ]]; then
        DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc-${HOST_ARCH}-apple-darwin"
        DEFAULT_PREFIX="${HOME:-$SOURCE_DIR}/.local/whp-qemu"
    else
        DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc"
        DEFAULT_PREFIX=/emulator
    fi

    BUILD_DIR="${BUILD_DIR:-$DEFAULT_BUILD_DIR}"
    PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
    BUILD_QEMU_IMG="${BUILD_QEMU_IMG:-1}"
    BUILD_QEMU_SYSTEM_I386="${BUILD_QEMU_SYSTEM_I386:-1}"
    BUILD_QEMU_SYSTEM_PPC="${BUILD_QEMU_SYSTEM_PPC:-1}"
    QEMU_TARGET_LIST=
    if [[ "$BUILD_QEMU_SYSTEM_PPC" == 1 ]]; then
        QEMU_TARGET_LIST=ppc-softmmu
    fi
    if [[ "$BUILD_QEMU_SYSTEM_I386" == 1 ]]; then
        QEMU_TARGET_LIST="${QEMU_TARGET_LIST:+$QEMU_TARGET_LIST,}i386-softmmu"
    fi
    BUILD_TARGETS="${BUILD_TARGETS:-all}"
    INSTALL="${INSTALL:-1}"
    MACOS_ENABLE_COCOA="${MACOS_ENABLE_COCOA:-1}"
    MACOS_ENABLE_COREAUDIO="${MACOS_ENABLE_COREAUDIO:-1}"
    MACOS_ENABLE_GTK="${MACOS_ENABLE_GTK:-1}"
    MACOS_ENABLE_PA="${MACOS_ENABLE_PA:-1}"
    QEMU_HOST_LTO="${QEMU_HOST_LTO:-$APPLE_SILICON_NATIVE}"
    BUILD_OPENBIOS="${BUILD_OPENBIOS:-1}"
    OPENBIOS_CROSS_COMPILE="${OPENBIOS_CROSS_COMPILE:-}"
    OPENBIOS_FORCE_RECONFIGURE="${OPENBIOS_FORCE_RECONFIGURE:-0}"
    BOOTSTRAP_POWERPC_TOOLCHAIN="${BOOTSTRAP_POWERPC_TOOLCHAIN:-1}"
    POWERPC_TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
    POWERPC_TOOLCHAIN_COMPILER="${POWERPC_TOOLCHAIN_COMPILER:-clang}"
    POWERPC_TOOLCHAIN_SOURCE_MODE="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
    POWERPC_TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$BUILD_DIR/firmware-tools/powerpc-elf}"
    POWERPC_TOOLCHAIN_ROOT="$(dirname "$POWERPC_TOOLCHAIN_DIR")"
    POWERPC_TOOLCHAIN_WORK_DIR="$POWERPC_TOOLCHAIN_ROOT/toolchain-work/powerpc-elf"
    POWERPC_TOOLCHAIN_DOWNLOAD_DIR="$POWERPC_TOOLCHAIN_ROOT/toolchain-downloads"

    whp_require_boolean_values \
        BUILD_QEMU_IMG BUILD_QEMU_SYSTEM_I386 BUILD_QEMU_SYSTEM_PPC \
        INSTALL MACOS_ENABLE_COCOA MACOS_ENABLE_COREAUDIO \
        MACOS_ENABLE_GTK MACOS_ENABLE_PA QEMU_HOST_LTO \
        BUILD_OPENBIOS OPENBIOS_FORCE_RECONFIGURE \
        BOOTSTRAP_POWERPC_TOOLCHAIN POWERPC_TOOLCHAIN_FORCE_REBUILD || exit 1

    for build_path in "$SOURCE_DIR" "$BUILD_DIR"; do
        case "$build_path" in
            *[' ':]*)
                printf 'error: QEMU source and build paths cannot contain spaces or colons\n' >&2
                exit 1
                ;;
        esac
    done

    export CFLAGS="${CFLAGS:--g0 -pipe -w}"
    reject_global_lto_flags
}

whp_prepare_host_tools()
{
    if [[ "$HOST_OS" == Darwin ]]; then
        # The macOS wrapper owns SDK and compiler-family selection.  The generic
        # stage consumes that resolved policy instead of discovering it again.
        : "${DEVELOPER_DIR:?macOS wrapper did not set DEVELOPER_DIR}"
        : "${SDKROOT:?macOS wrapper did not set SDKROOT}"
        : "${MACOS_SDK_VERSION:?macOS wrapper did not set MACOS_SDK_VERSION}"
        : "${CC:?macOS wrapper did not set CC}"
        : "${CXX:?macOS wrapper did not set CXX}"
        : "${OBJC:?macOS wrapper did not set OBJC}"
        : "${CC_FOR_BUILD:?macOS wrapper did not set CC_FOR_BUILD}"
        : "${CXX_FOR_BUILD:?macOS wrapper did not set CXX_FOR_BUILD}"
        : "${OBJC_FOR_BUILD:?macOS wrapper did not set OBJC_FOR_BUILD}"

        if [[ -z "${STRIP_FOR_BUILD:-}" ]]; then
            STRIP_FOR_BUILD="$(xcrun --sdk macosx --find strip)"
            export STRIP_FOR_BUILD
        fi
        export PKG_CONFIG_FOR_BUILD="${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"

        if [[ "$MACOS_ARCH_FLAGS" == 1 ]]; then
            whp_append_flag CFLAGS "-arch $HOST_ARCH"
            whp_append_flag CXXFLAGS "-arch $HOST_ARCH"
            whp_append_flag OBJCFLAGS "-arch $HOST_ARCH"
            whp_append_flag LDFLAGS "-arch $HOST_ARCH"
        fi

        if command -v brew >/dev/null 2>&1; then
            HOMEBREW_PREFIX="${HOMEBREW_PREFIX:-$(brew --prefix)}"
            case "$HOST_ARCH" in
                arm64) expected_homebrew_prefix=/opt/homebrew ;;
                x86_64) expected_homebrew_prefix=/usr/local ;;
            esac
            if [[ "$HOMEBREW_PREFIX" != "$expected_homebrew_prefix" &&
                  "$MACOS_ALLOW_MIXED_HOMEBREW" != 1 ]]; then
                printf '%s\n' \
                    "error: Homebrew prefix $HOMEBREW_PREFIX does not match $HOST_ARCH." \
                    "expected: $expected_homebrew_prefix" \
                    'set MACOS_ALLOW_MIXED_HOMEBREW=1 only for an intentional custom layout.' >&2
                exit 1
            fi
            export PATH="$HOMEBREW_PREFIX/bin:$PATH"
            homebrew_pc="$HOMEBREW_PREFIX/lib/pkgconfig:$HOMEBREW_PREFIX/share/pkgconfig"
            export PKG_CONFIG_PATH="$homebrew_pc${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
            export PKG_CONFIG_PATH_FOR_BUILD="${PKG_CONFIG_PATH_FOR_BUILD:-$PKG_CONFIG_PATH}"
        fi
    else
        export CC_FOR_BUILD="${CC_FOR_BUILD:-${CC:-cc}}"
        export CXX_FOR_BUILD="${CXX_FOR_BUILD:-${CXX:-c++}}"
        export OBJC_FOR_BUILD="${OBJC_FOR_BUILD:-${OBJC:-$CC_FOR_BUILD}}"
        export STRIP_FOR_BUILD="${STRIP_FOR_BUILD:-strip}"
        export PKG_CONFIG_FOR_BUILD="${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"
    fi

    if command -v ccache >/dev/null 2>&1; then
        if [[ -z "${CC:-}" ]]; then
            export CC="ccache cc"
        elif ! compiler_has_cache_wrapper "$CC"; then
            export CC="ccache $CC"
        fi
        if [[ -z "${CXX:-}" ]]; then
            export CXX="ccache c++"
        elif ! compiler_has_cache_wrapper "$CXX"; then
            export CXX="ccache $CXX"
        fi
    fi
}

whp_prepare_build_tools()
{
    if command -v nproc >/dev/null 2>&1; then
        DEFAULT_JOBS="$(nproc)"
    elif command -v sysctl >/dev/null 2>&1; then
        DEFAULT_JOBS="$(sysctl -n hw.ncpu 2>/dev/null || printf '1')"
    else
        DEFAULT_JOBS=1
    fi
    JOBS="${JOBS:-$DEFAULT_JOBS}"

    if [[ -z "${MAKE_CMD:-}" ]]; then
        if command -v gmake >/dev/null 2>&1; then
            MAKE_CMD=gmake
        else
            MAKE_CMD=make
        fi
    fi
    if ! "$MAKE_CMD" --version 2>/dev/null | head -n 1 | grep -q 'GNU Make'; then
        printf 'error: QEMU requires GNU Make; set MAKE_CMD to a GNU Make binary\n' >&2
        exit 1
    fi
    export MAKE="$MAKE_CMD"
}

whp_prepare_configure_args()
{
    configure_args=(
        --cc="${CC:-cc}"
        --host-cc="$CC_FOR_BUILD"
        --cxx="${CXX:-c++}"
        --enable-pixman
        --enable-slirp
        --enable-tcg
        --prefix="$PREFIX"
    )

    if [[ -n "$QEMU_TARGET_LIST" ]]; then
        configure_args+=(--target-list="$QEMU_TARGET_LIST")
    else
        configure_args+=(--disable-system)
    fi

    if [[ "$BUILD_QEMU_IMG" == 1 ]]; then
        configure_args+=(--enable-tools)
    else
        configure_args+=(--disable-tools)
    fi

    if [[ "$QEMU_HOST_LTO" == 1 ]]; then
        configure_args+=(--enable-lto)
    else
        configure_args+=(--disable-lto)
    fi

    if [[ "$HOST_OS" == Darwin ]]; then
        macos_audio_drivers=
        configure_args+=(--objcc="$OBJC")

        if [[ "$MACOS_ENABLE_COCOA" == 1 ]]; then
            configure_args+=(--enable-cocoa)
        else
            configure_args+=(--disable-cocoa)
        fi

        if [[ "$MACOS_ENABLE_COREAUDIO" == 1 ]]; then
            configure_args+=(--enable-coreaudio)
            macos_audio_drivers=coreaudio
        else
            configure_args+=(--disable-coreaudio)
        fi

        if [[ "$MACOS_ENABLE_GTK" == 1 ]]; then
            configure_args+=(--enable-gtk)
        else
            configure_args+=(--disable-gtk)
        fi

        if [[ "$MACOS_ENABLE_PA" == 1 ]]; then
            configure_args+=(--enable-pa)
            if [[ -n "$macos_audio_drivers" ]]; then
                macos_audio_drivers+=,pa
            else
                macos_audio_drivers=pa
            fi
        else
            configure_args+=(--disable-pa)
        fi

        if [[ -n "$macos_audio_drivers" ]]; then
            configure_args+=(--audio-drv-list="$macos_audio_drivers")
        fi
    else
        configure_args+=(--enable-gtk --enable-pa)
    fi
}

whp_prepare_build()
{
    whp_prepare_host_identity
    whp_prepare_build_defaults
    whp_prepare_host_tools
    whp_prepare_build_tools
    whp_prepare_configure_args
}
