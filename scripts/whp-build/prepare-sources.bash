# WHP source, toolchain-probe, and firmware preparation stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_prepare_sources()
{
    local openbios_mode="${BUILD_OPENBIOS:-auto}"
    local bootstrap_mode="${BOOTSTRAP_POWERPC_TOOLCHAIN:-auto}"
    local powerpc_toolchain_compiler="${POWERPC_TOOLCHAIN_COMPILER:-clang}"
    local llvm_submodule_path="${POWERPC_LLVM_SUBMODULE_PATH:-toolchains/llvm-project}"
    local openbios_auto=0
    local source_prepare_failed=0

    case "$openbios_mode" in
        auto)
            openbios_auto=1
            case ",${QEMU_TARGET_LIST:-}," in
                *,ppc-softmmu,*) BUILD_OPENBIOS=1 ;;
                *) BUILD_OPENBIOS=0 ;;
            esac
            ;;
        0|1) BUILD_OPENBIOS="$openbios_mode" ;;
        *)
            printf 'error: BUILD_OPENBIOS must be auto, 0, or 1\n' >&2
            return 1
            ;;
    esac

    if [[ "$BUILD_OPENBIOS" == 1 ]]; then
        case "$powerpc_toolchain_compiler" in
            clang|gcc) ;;
            *)
                if [[ "$openbios_auto" == 1 ]]; then
                    printf 'OpenBIOS auto: unsupported compiler lane %s; continuing without WHP firmware build\n' \
                        "$powerpc_toolchain_compiler" >&2
                    BUILD_OPENBIOS=0
                else
                    printf 'error: POWERPC_TOOLCHAIN_COMPILER must be clang or gcc\n' >&2
                    return 1
                fi
                ;;
        esac
    fi

    if [[ "$BUILD_OPENBIOS" == 1 ]]; then
        case "$bootstrap_mode" in
            auto)
                if [[ -n "${OPENBIOS_CROSS_COMPILE:-}" ]]; then
                    BOOTSTRAP_POWERPC_TOOLCHAIN=0
                else
                    BOOTSTRAP_POWERPC_TOOLCHAIN=1
                fi
                ;;
            0|1) BOOTSTRAP_POWERPC_TOOLCHAIN="$bootstrap_mode" ;;
            *)
                printf 'error: BOOTSTRAP_POWERPC_TOOLCHAIN must be auto, 0, or 1\n' >&2
                return 1
                ;;
        esac

        if [[ -z "${MAKE_CMD:-}" ]]; then
            if [[ "$openbios_auto" == 1 ]]; then
                printf '%s\n' \
                    'OpenBIOS auto: Make is unavailable; continuing with the core QEMU build.' >&2
                BUILD_OPENBIOS=0
                BOOTSTRAP_POWERPC_TOOLCHAIN=0
            else
                printf '%s\n' \
                    'error: OpenBIOS was explicitly requested but no Make implementation is available.' >&2
                return 1
            fi
        fi
    else
        BOOTSTRAP_POWERPC_TOOLCHAIN=0
    fi

    # Existing clones cache submodule URLs in .git/config. Source preparation
    # only touches firmware/toolchain submodules when the firmware lane remains
    # selected. A failure in auto mode is a feature decline, not a QEMU failure.
    if [[ "$BUILD_OPENBIOS" == 1 && -e "$SOURCE_DIR/.git" ]]; then
        if ! command -v git >/dev/null 2>&1; then
            if [[ "$openbios_auto" == 1 ]]; then
                printf '%s\n' \
                    'OpenBIOS auto: git is unavailable; continuing without WHP firmware build.' >&2
                BUILD_OPENBIOS=0
                BOOTSTRAP_POWERPC_TOOLCHAIN=0
            else
                printf 'error: git is required to prepare OpenBIOS/toolchain sources\n' >&2
                return 1
            fi
        else
            powerpc_source_submodules=(roms/openbios)
            if [[ "$powerpc_toolchain_compiler" == clang ]]; then
                powerpc_source_submodules+=("$llvm_submodule_path")
            fi

            if ! git -C "$SOURCE_DIR" submodule sync -- "${powerpc_source_submodules[@]}" ||
               ! git -C "$SOURCE_DIR" submodule update --init -- "${powerpc_source_submodules[@]}"; then
                source_prepare_failed=1
            fi
            if [[ "$source_prepare_failed" == 1 ]]; then
                if [[ "$openbios_auto" == 1 ]]; then
                    printf '%s\n' \
                        'OpenBIOS auto: firmware/toolchain sources could not be prepared; continuing with core QEMU.' >&2
                    BUILD_OPENBIOS=0
                    BOOTSTRAP_POWERPC_TOOLCHAIN=0
                else
                    printf 'error: failed to prepare OpenBIOS/toolchain submodules\n' >&2
                    return 1
                fi
            fi
        fi
    fi

    mkdir -p "$BUILD_DIR"

    MACOS_COMPILER_MANIFEST=disabled
    MACOS_COMPILER_MANIFEST_SIGNATURE=disabled
    if [[ "$HOST_OS" == Darwin && "$MACOS_VERIFY_TOOLCHAIN" == 1 ]]; then
        MACOS_COMPILER_MANIFEST="$BUILD_DIR/.whp-macos-toolchain"
        MACOS_COMPILER_MANIFEST="$MACOS_COMPILER_MANIFEST" \
        MACOS_COMPILER_PROBE_DIR="$BUILD_DIR/.whp-macos-toolchain.d" \
            "$WHP_BUILD_BASH" --noprofile --norc \
                "$SOURCE_DIR/scripts/verify-macos-toolchain.sh"
        MACOS_COMPILER_MANIFEST_SIGNATURE="$(cksum "$MACOS_COMPILER_MANIFEST" |
            awk '{print $1 ":" $2}')"
    fi

    MACOS_LTO_MANIFEST=disabled
    MACOS_LTO_MANIFEST_SIGNATURE=disabled
    if [[ "$HOST_OS" == Darwin && "$QEMU_HOST_LTO" == 1 ]]; then
        MACOS_LTO_MANIFEST="$BUILD_DIR/.whp-macos-lto"
        MACOS_LTO_MANIFEST="$MACOS_LTO_MANIFEST" \
        MACOS_LTO_PROBE_DIR="$BUILD_DIR/.whp-macos-lto.d" \
            "$WHP_BUILD_BASH" --noprofile --norc \
                "$SOURCE_DIR/scripts/verify-macos-lto.sh"
        MACOS_LTO_MANIFEST_SIGNATURE="$(cksum "$MACOS_LTO_MANIFEST" |
            awk '{print $1 ":" $2}')"
    fi

    OPENBIOS_CONFIG_FILE="$BUILD_DIR/.whp-openbios-meson.env"
    if [[ "$BUILD_OPENBIOS" == 1 ]]; then
        if ! BUILD_DIR="$BUILD_DIR" \
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
            "$WHP_BUILD_BASH" --noprofile --norc \
                "$SOURCE_DIR/scripts/whp-build/configure-openbios.bash"; then
            if [[ "$openbios_auto" == 1 ]]; then
                printf '%s\n' \
                    'OpenBIOS auto: firmware preparation failed; continuing with the core QEMU build.' >&2
                BUILD_OPENBIOS=0
                BOOTSTRAP_POWERPC_TOOLCHAIN=0
                rm -f "$OPENBIOS_CONFIG_FILE"
            else
                printf 'error: explicitly requested OpenBIOS preparation failed\n' >&2
                return 1
            fi
        fi
    else
        rm -f "$OPENBIOS_CONFIG_FILE"
    fi

    export BUILD_OPENBIOS BOOTSTRAP_POWERPC_TOOLCHAIN
}
