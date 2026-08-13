# WHP source, toolchain-probe, and firmware preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_sources()
{
    powerpc_toolchain_compiler="${POWERPC_TOOLCHAIN_COMPILER:-}"
    llvm_submodule_path="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"

    if [[ "$BUILD_OPENBIOS" == "1" ]]; then
        if [[ -z "$powerpc_toolchain_compiler" ]]; then
            case "${HOST_OS:-$(uname -s)}" in
                Darwin) powerpc_toolchain_compiler=clang ;;
                *) powerpc_toolchain_compiler=gcc ;;
            esac
        fi
        case "$powerpc_toolchain_compiler" in
            clang|gcc) ;;
            *)
                printf 'error: POWERPC_TOOLCHAIN_COMPILER must be clang or gcc\n' >&2
                exit 1
                ;;
        esac
    fi

    # Existing clones cache submodule URLs in .git/config. Source preparation
    # owns mounting every source dependency required by the selected firmware
    # compiler lane before any bootstrap script consumes it. OpenBIOS is always
    # required; the pinned LLVM gitlink is required only by the Clang lane.
    if [[ "$BUILD_OPENBIOS" == "1" && -e "$SOURCE_DIR/.git" ]]; then
        if ! command -v git >/dev/null 2>&1; then
            printf 'error: git is required to mount OpenBIOS/toolchain sources\n' >&2
            exit 1
        fi

        powerpc_source_submodules=(roms/openbios)
        if [[ "$powerpc_toolchain_compiler" == clang ]]; then
            powerpc_source_submodules+=("$llvm_submodule_path")
        fi

        git -C "$SOURCE_DIR" submodule sync -- "${powerpc_source_submodules[@]}"
        git -C "$SOURCE_DIR" submodule update --init -- "${powerpc_source_submodules[@]}"
    fi

    mkdir -p "$BUILD_DIR"

    MACOS_COMPILER_MANIFEST=disabled
    MACOS_COMPILER_MANIFEST_SIGNATURE=disabled
    if [[ "$HOST_OS" == Darwin && "$MACOS_VERIFY_TOOLCHAIN" == 1 ]]; then
        MACOS_COMPILER_MANIFEST="$BUILD_DIR/.whp-macos-toolchain"
        MACOS_COMPILER_MANIFEST="$MACOS_COMPILER_MANIFEST" \
        MACOS_COMPILER_PROBE_DIR="$BUILD_DIR/.whp-macos-toolchain.d" \
            bash "$SOURCE_DIR/scripts/verify-macos-toolchain.sh"
        MACOS_COMPILER_MANIFEST_SIGNATURE="$(cksum "$MACOS_COMPILER_MANIFEST" |
            awk '{print $1 ":" $2}')"
    fi

    MACOS_LTO_MANIFEST=disabled
    MACOS_LTO_MANIFEST_SIGNATURE=disabled
    if [[ "$HOST_OS" == Darwin && "$QEMU_HOST_LTO" == 1 ]]; then
        MACOS_LTO_MANIFEST="$BUILD_DIR/.whp-macos-lto"
        MACOS_LTO_MANIFEST="$MACOS_LTO_MANIFEST" \
        MACOS_LTO_PROBE_DIR="$BUILD_DIR/.whp-macos-lto.d" \
            bash "$SOURCE_DIR/scripts/verify-macos-lto.sh"
        MACOS_LTO_MANIFEST_SIGNATURE="$(cksum "$MACOS_LTO_MANIFEST" |
            awk '{print $1 ":" $2}')"
    fi

    OPENBIOS_CONFIG_FILE="$BUILD_DIR/.whp-openbios-meson.env"
    if [[ "$BUILD_OPENBIOS" == "1" ]]; then
        # configure-openbios.bash is a subprocess boundary. Pass the exact
        # compiler/submodule lane selected above so source preparation and
        # firmware configuration cannot independently choose different inputs.
        BUILD_DIR="$BUILD_DIR" \
        OPENBIOS_DIR="${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}" \
        OPENBIOS_TOOLS_DIR="${OPENBIOS_TOOLS_DIR:-$BUILD_DIR/firmware-tools}" \
        OPENBIOS_CROSS_COMPILE="$OPENBIOS_CROSS_COMPILE" \
        OPENBIOS_FORCE_RECONFIGURE="$OPENBIOS_FORCE_RECONFIGURE" \
        BOOTSTRAP_POWERPC_TOOLCHAIN="$BOOTSTRAP_POWERPC_TOOLCHAIN" \
        POWERPC_TOOLCHAIN_FORCE_REBUILD="$POWERPC_TOOLCHAIN_FORCE_REBUILD" \
        POWERPC_TOOLCHAIN_SOURCE_MODE="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}" \
        POWERPC_TOOLCHAIN_COMPILER="$powerpc_toolchain_compiler" \
        POWERPC_LLVM_SUBMODULE_PATH="$llvm_submodule_path" \
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
