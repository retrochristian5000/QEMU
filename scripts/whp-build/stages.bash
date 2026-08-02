# WHP build-stage implementation.  builder.sh sources this file and runs its
# stages in order; this file is not a public entry point.

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: the WHP build system requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi
: "${SOURCE_DIR:?builder.sh must define SOURCE_DIR before loading the build system}"

canonical_macos_arch()
{
    case "$1" in
        arm64|aarch64) printf 'arm64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

append_flag()
{
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"

    if [[ -n "$current" ]]; then
        printf -v "$variable" '%s %s' "$current" "$value"
    else
        printf -v "$variable" '%s' "$value"
    fi
    export "$variable"
}

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

whp_prepare_build()
{
HOST_OS="$(uname -s)"
PROCESS_ARCH="$(uname -m)"
HOST_ARCH="$PROCESS_ARCH"
PHYSICAL_ARCH="$PROCESS_ARCH"
ROSETTA_TRANSLATED=0
APPLE_SILICON_HOST=0
APPLE_SILICON_NATIVE=0

if [[ "$HOST_OS" == "Darwin" ]]; then
    if [[ "$(sysctl -in hw.optional.arm64 2>/dev/null || printf '0')" == "1" ]]; then
        PHYSICAL_ARCH=arm64
        APPLE_SILICON_HOST=1
    fi
    if [[ "$(sysctl -in sysctl.proc_translated 2>/dev/null || printf '0')" == "1" ]]; then
        ROSETTA_TRANSLATED=1
    fi

    HOST_ARCH="$(canonical_macos_arch "$PROCESS_ARCH")" || {
        printf 'error: unsupported macOS process architecture: %s\n' "$PROCESS_ARCH" >&2
        exit 1
    }
    PHYSICAL_ARCH="$(canonical_macos_arch "$PHYSICAL_ARCH")" || {
        printf 'error: unsupported macOS physical architecture: %s\n' "$PHYSICAL_ARCH" >&2
        exit 1
    }
    if [[ "$PHYSICAL_ARCH" == "arm64" && "$HOST_ARCH" == "arm64" ]]; then
        APPLE_SILICON_NATIVE=1
    fi
fi

MACOS_ALLOW_ROSETTA="${MACOS_ALLOW_ROSETTA:-0}"
MACOS_HOST_ARCH="${MACOS_HOST_ARCH:-$HOST_ARCH}"
MACOS_ALLOW_MIXED_HOMEBREW="${MACOS_ALLOW_MIXED_HOMEBREW:-0}"
MACOS_ARCH_FLAGS="${MACOS_ARCH_FLAGS:-1}"
MACOS_VERIFY_TOOLCHAIN="${MACOS_VERIFY_TOOLCHAIN:-1}"
MACOS_ALLOW_NONCLANG="${MACOS_ALLOW_NONCLANG:-0}"
MACOS_ALLOW_COMPILER_CONFIG="${MACOS_ALLOW_COMPILER_CONFIG:-0}"

for boolean_value in \
    MACOS_ALLOW_ROSETTA MACOS_ALLOW_MIXED_HOMEBREW MACOS_ARCH_FLAGS \
    MACOS_VERIFY_TOOLCHAIN MACOS_ALLOW_NONCLANG MACOS_ALLOW_COMPILER_CONFIG; do
    case "${!boolean_value}" in
        0|1) ;;
        *) printf 'error: %s must be 0 or 1\n' "$boolean_value" >&2; exit 1 ;;
    esac
done

if [[ "$HOST_OS" == "Darwin" ]]; then
    MACOS_HOST_ARCH="$(canonical_macos_arch "$MACOS_HOST_ARCH")" || {
        printf 'error: MACOS_HOST_ARCH must be arm64 or x86_64\n' >&2
        exit 1
    }

    if [[ "$MACOS_HOST_ARCH" != "$HOST_ARCH" ]]; then
        printf '%s\n' \
            "error: cross-host macOS builds are not enabled by builder.sh." \
            "requested host: $MACOS_HOST_ARCH; running process: $HOST_ARCH" \
            'run the build under the requested architecture, for example:' \
            '  arch -arm64 ./builder.sh' \
            '  arch -x86_64 env MACOS_ALLOW_ROSETTA=1 ./builder.sh' >&2
        exit 1
    fi

    if [[ "$ROSETTA_TRANSLATED" == "1" && "$MACOS_ALLOW_ROSETTA" != "1" ]]; then
        printf '%s\n' \
            'error: the build is running under Rosetta translation.' \
            'rerun natively with: arch -arm64 ./builder.sh' \
            'or explicitly allow an x86_64 build with:' \
            '  MACOS_ALLOW_ROSETTA=1 ./builder.sh' >&2
        exit 1
    fi
fi

if [[ "$HOST_OS" == "Darwin" ]]; then
    DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc-${MACOS_HOST_ARCH}-apple-darwin"
    DEFAULT_PREFIX="${HOME:-$SOURCE_DIR}/.local/whp-qemu"
else
    DEFAULT_BUILD_DIR="$SOURCE_DIR/build/whp-ppc"
    DEFAULT_PREFIX="/emulator"
fi

BUILD_DIR="${BUILD_DIR:-$DEFAULT_BUILD_DIR}"
PREFIX="${PREFIX:-$DEFAULT_PREFIX}"
QEMU_TARGET_LIST="${QEMU_TARGET_LIST:-ppc-softmmu}"
BUILD_TARGETS="${BUILD_TARGETS:-all}"
INSTALL="${INSTALL:-0}"
MACOS_ENABLE_GTK="${MACOS_ENABLE_GTK:-0}"
MACOS_ENABLE_PA="${MACOS_ENABLE_PA:-0}"
QEMU_HOST_LTO="${QEMU_HOST_LTO:-$APPLE_SILICON_NATIVE}"
BUILD_OPENBIOS="${BUILD_OPENBIOS:-1}"
OPENBIOS_CROSS_COMPILE="${OPENBIOS_CROSS_COMPILE:-}"
OPENBIOS_FORCE_RECONFIGURE="${OPENBIOS_FORCE_RECONFIGURE:-0}"
BOOTSTRAP_POWERPC_TOOLCHAIN="${BOOTSTRAP_POWERPC_TOOLCHAIN:-1}"
POWERPC_TOOLCHAIN_FORCE_REBUILD="${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
POWERPC_TOOLCHAIN_DIR="${POWERPC_TOOLCHAIN_DIR:-$BUILD_DIR/firmware-tools/powerpc-elf}"
POWERPC_TOOLCHAIN_WORK_DIR="${POWERPC_TOOLCHAIN_WORK_DIR:-$BUILD_DIR/firmware-tools/toolchain-work/powerpc-elf}"
POWERPC_TOOLCHAIN_DOWNLOAD_DIR="${POWERPC_TOOLCHAIN_DOWNLOAD_DIR:-$BUILD_DIR/firmware-tools/toolchain-downloads}"

for boolean_value in \
    INSTALL MACOS_ENABLE_GTK MACOS_ENABLE_PA QEMU_HOST_LTO \
    BUILD_OPENBIOS OPENBIOS_FORCE_RECONFIGURE \
    BOOTSTRAP_POWERPC_TOOLCHAIN POWERPC_TOOLCHAIN_FORCE_REBUILD; do
    case "${!boolean_value}" in
        0|1) ;;
        *) printf 'error: %s must be 0 or 1\n' "$boolean_value" >&2; exit 1 ;;
    esac
done

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

if [[ "$HOST_OS" == "Darwin" ]]; then
    if ! command -v xcrun >/dev/null 2>&1; then
        printf 'error: xcrun is missing; install the Xcode Command Line Tools\n' >&2
        exit 1
    fi

    export DEVELOPER_DIR="${DEVELOPER_DIR:-$(xcode-select -p 2>/dev/null || true)}"
    export SDKROOT="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
    MACOS_SDK_VERSION="$(xcrun --sdk macosx --show-sdk-version 2>/dev/null || printf 'unknown')"
    if [[ ! -d "$SDKROOT" ]]; then
        printf 'error: macOS SDK not found at %s\n' "$SDKROOT" >&2
        exit 1
    fi

    DARWIN_CLANG="$(xcrun --sdk macosx --find clang)"
    DARWIN_CLANGXX="$(xcrun --sdk macosx --find clang++)"
    DARWIN_STRIP="$(xcrun --sdk macosx --find strip)"

    export CC_FOR_BUILD="${CC_FOR_BUILD:-$DARWIN_CLANG}"
    export CXX_FOR_BUILD="${CXX_FOR_BUILD:-$DARWIN_CLANGXX}"
    export OBJC_FOR_BUILD="${OBJC_FOR_BUILD:-$DARWIN_CLANG}"
    export STRIP_FOR_BUILD="${STRIP_FOR_BUILD:-$DARWIN_STRIP}"
    export PKG_CONFIG_FOR_BUILD="${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"

    if [[ -z "${CC:-}" ]]; then
        export CC="$DARWIN_CLANG"
    fi
    if [[ -z "${CXX:-}" ]]; then
        export CXX="$DARWIN_CLANGXX"
    fi
    if [[ -z "${OBJC:-}" ]]; then
        export OBJC="$DARWIN_CLANG"
    fi

    if [[ "$MACOS_ARCH_FLAGS" == "1" ]]; then
        append_flag CFLAGS "-arch $MACOS_HOST_ARCH"
        append_flag CXXFLAGS "-arch $MACOS_HOST_ARCH"
        append_flag OBJCFLAGS "-arch $MACOS_HOST_ARCH"
        append_flag LDFLAGS "-arch $MACOS_HOST_ARCH"
    fi

    if command -v brew >/dev/null 2>&1; then
        HOMEBREW_PREFIX="${HOMEBREW_PREFIX:-$(brew --prefix)}"
        case "$MACOS_HOST_ARCH" in
            arm64) expected_homebrew_prefix=/opt/homebrew ;;
            x86_64) expected_homebrew_prefix=/usr/local ;;
        esac
        if [[ "$HOMEBREW_PREFIX" != "$expected_homebrew_prefix" &&
              "$MACOS_ALLOW_MIXED_HOMEBREW" != "1" ]]; then
            printf '%s\n' \
                "error: Homebrew prefix $HOMEBREW_PREFIX does not match $MACOS_HOST_ARCH." \
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
    export OBJC_FOR_BUILD="${OBJC_FOR_BUILD:-${OBJC:-${CC_FOR_BUILD}}}"
    export STRIP_FOR_BUILD="${STRIP_FOR_BUILD:-strip}"
    export PKG_CONFIG_FOR_BUILD="${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"
fi

# Reuse compiler output for QEMU host objects without changing the compilers
# used to build executable build-machine tools such as toke and cross GCC.
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
    --cc="${CC:-cc}"
    --host-cc="$CC_FOR_BUILD"
    --cxx="${CXX:-c++}"
    --enable-pixman
    --enable-slirp
    --enable-tools
    --enable-tcg
    --prefix="$PREFIX"
    --target-list="$QEMU_TARGET_LIST"
)

# Meson owns the LTO flags for QEMU host artifacts. Do not add -flto to the
# process environment: those flags would also reach firmware and build tools.
if [[ "$QEMU_HOST_LTO" == "1" ]]; then
    configure_args+=(--enable-lto)
else
    configure_args+=(--disable-lto)
fi

if [[ "$HOST_OS" == "Darwin" ]]; then
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
}

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
    MACOS_HOST_ARCH="$MACOS_HOST_ARCH" \
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
    MACOS_HOST_ARCH="$MACOS_HOST_ARCH" \
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
    OPENBIOS_HOSTCC="${OPENBIOS_HOSTCC:-$CC_FOR_BUILD}" \
    OPENBIOS_HOSTCXX="${OPENBIOS_HOSTCXX:-$CXX_FOR_BUILD}" \
    OPENBIOS_HOSTSTRIP="${OPENBIOS_HOSTSTRIP:-$STRIP_FOR_BUILD}" \
    OPENBIOS_CROSS_COMPILE="$OPENBIOS_CROSS_COMPILE" \
    OPENBIOS_FORCE_RECONFIGURE="$OPENBIOS_FORCE_RECONFIGURE" \
    BOOTSTRAP_POWERPC_TOOLCHAIN="$BOOTSTRAP_POWERPC_TOOLCHAIN" \
    POWERPC_TOOLCHAIN_FORCE_REBUILD="$POWERPC_TOOLCHAIN_FORCE_REBUILD" \
    POWERPC_TOOLCHAIN_SOURCE_MODE="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}" \
    POWERPC_TOOLCHAIN_DIR="$POWERPC_TOOLCHAIN_DIR" \
    POWERPC_TOOLCHAIN_WORK_DIR="$POWERPC_TOOLCHAIN_WORK_DIR" \
    POWERPC_TOOLCHAIN_DOWNLOAD_DIR="$POWERPC_TOOLCHAIN_DOWNLOAD_DIR" \
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

whp_configure_build()
{
# Reconfigure only when the build machine, host toolchain, SDK, dependencies,
# firmware toolchain, or requested QEMU settings change.
config_file="$BUILD_DIR/.whp-config"
config_candidate="$config_file.new"
{
    printf 'HOST_OS=%s\n' "$HOST_OS"
    printf 'PROCESS_ARCH=%s\n' "$PROCESS_ARCH"
    printf 'PHYSICAL_ARCH=%s\n' "$PHYSICAL_ARCH"
    printf 'HOST_ARCH=%s\n' "$HOST_ARCH"
    printf 'ROSETTA_TRANSLATED=%s\n' "$ROSETTA_TRANSLATED"
    printf 'MACOS_HOST_ARCH=%s\n' "$MACOS_HOST_ARCH"
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

whp_build_targets()
{
local build_target_list=()
if (( $# > 0 )); then
    build_target_list=("$@")
else
    read -r -a build_target_list <<< "$BUILD_TARGETS"
fi
"$MAKE_CMD" -C "$BUILD_DIR" -j"$JOBS" "${build_target_list[@]}"

# Installation is deliberately separate from compilation so routine rebuilds
# do not recopy the full output tree. Use INSTALL=1 when an install is needed.
if [[ "$INSTALL" == "1" ]]; then
    "$MAKE_CMD" -C "$BUILD_DIR" install
fi
}
