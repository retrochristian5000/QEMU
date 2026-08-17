# WHP configuration identity and configure execution stage.
# SPDX-License-Identifier: GPL-2.0-or-later

whp_configure_previous_target_list()
{
    local path="$1"
    local line
    local value
    local arg

    [[ -f "$path" ]] || return 0

    while IFS= read -r line; do
        case "$line" in
            QEMU_TARGET_LIST=*)
                printf '%s\n' "${line#QEMU_TARGET_LIST=}"
                return 0
                ;;
        esac
    done < "$path"

    # Backward compatibility for build trees created before QEMU_TARGET_LIST
    # had its own identity field.  CONFIGURE_ARG is sufficient to recover the
    # old target set without forcing users to throw the tree away once.
    while IFS= read -r line; do
        case "$line" in
            CONFIGURE_ARG=*)
                value="${line#CONFIGURE_ARG=}"
                for arg in $value; do
                    case "$arg" in
                        --target-list=*)
                            printf '%s\n' "${arg#--target-list=}"
                            return 0
                            ;;
                    esac
                done
                ;;
        esac
    done < "$path"
}

whp_configure_add_target()
{
    local target="$1"

    [[ -n "$target" ]] || return 0
    case ",${QEMU_TARGET_LIST:-}," in
        *",$target,"*) return 0 ;;
    esac
    QEMU_TARGET_LIST="${QEMU_TARGET_LIST:+$QEMU_TARGET_LIST,}$target"
}

whp_configure_merge_previous_targets()
{
    local config_file="$1"
    local current="${QEMU_TARGET_LIST:-}"
    local previous
    local target
    local current_targets=()
    local previous_targets=()

    [[ "${WHP_INCREMENTAL_BUILD:-1}" == 1 ]] || return 0
    previous="$(whp_configure_previous_target_list "$config_file")"
    [[ -n "$previous" ]] || return 0

    # Preserve the established target order first, then append genuinely new
    # targets from this invocation.  Reversing that order based on whichever
    # target the user requested would change CONFIGURE_ARG despite an identical
    # target set and cause pointless reconfigure churn on alternating builds.
    QEMU_TARGET_LIST=
    IFS=, read -r -a previous_targets <<< "$previous"
    for target in "${previous_targets[@]}"; do
        whp_configure_add_target "$target"
    done
    IFS=, read -r -a current_targets <<< "$current"
    for target in "${current_targets[@]}"; do
        whp_configure_add_target "$target"
    done
}

whp_configure_sync_target_args()
{
    local arg
    local synced=()

    for arg in "${configure_args[@]}"; do
        case "$arg" in
            --target-list=*|--disable-system) ;;
            *) synced+=("$arg") ;;
        esac
    done

    if [[ -n "${QEMU_TARGET_LIST:-}" ]]; then
        synced+=("--target-list=$QEMU_TARGET_LIST")
    else
        synced+=(--disable-system)
    fi
    configure_args=("${synced[@]}")
}

whp_configure_build()
{
local ppc_custom_devices=0
local ppc_generated_config=""
local ppc_generated_temp=""
local configure_status=0
local config_file="$BUILD_DIR/.whp-config"
local config_candidate="$BUILD_DIR/.whp-config.new"
local stale_ppc_config=""

# Incremental target selection is monotonic.  Reconfiguring QEMU in place to
# add a target is safe; removing an already-configured target would make old
# outputs disappear from the same build tree and turns a small follow-up build
# into an avoidable restart.  WHP_INCREMENTAL_BUILD=0 intentionally opts out.
whp_configure_merge_previous_targets "$config_file"
whp_configure_sync_target_args

# QEMU's tracked ppc-softmmu defaults already include both Old World and New
# World Macintosh boards. Do not generate a source-tree preset for that common
# case. Only an explicit machine filter needs the compatibility preset hook.
WHP_PPC_DEVICE_CONFIG_SIGNATURE=not-requested
case ",${QEMU_TARGET_LIST:-}," in
    *,ppc-softmmu,*)
        if [[ "${CONFIG_MAC_NEWWORLD:-y}" == y &&
              "${CONFIG_MAC_OLDWORLD:-y}" == y ]]; then
            WHP_PPC_DEVICE_CONFIG_SIGNATURE=tracked-defaults
            stale_ppc_config="$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
            if [[ -f "$stale_ppc_config" ]] &&
               grep -Fq '# WHP user overrides generated from .whpconfig; do not edit.' \
                   "$stale_ppc_config"; then
                rm -f "$stale_ppc_config"
            fi
        else
            ppc_custom_devices=1
            WHP_PPC_DEVICE_CONFIG_SIGNATURE="newworld=${CONFIG_MAC_NEWWORLD:-y};oldworld=${CONFIG_MAC_OLDWORLD:-y}"
            configure_args+=(--with-devices-ppc=whp-user)
        fi
        ;;
esac

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
    printf 'CFLAGS=%s\n' "${CFLAGS:-}"
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
    printf 'MAKE=%s\n' "${MAKE_CMD:-}"
    printf 'NINJA=%s\n' "${NINJA_CMD:-${NINJA:-}}"
    printf 'PYTHON=%s\n' "${PYTHON:-}"
    printf 'SOURCE_DIR=%s\n' "$SOURCE_DIR"
    printf 'QEMU_TARGET_LIST=%s\n' "${QEMU_TARGET_LIST:-}"
    printf 'QEMU_HOST_LTO=%s\n' "$QEMU_HOST_LTO"
    printf 'BUILD_OPENBIOS=%s\n' "$BUILD_OPENBIOS"
    printf 'OPENBIOS_CROSS_COMPILE=%s\n' "$OPENBIOS_CROSS_COMPILE"
    printf 'BOOTSTRAP_POWERPC_TOOLCHAIN=%s\n' "$BOOTSTRAP_POWERPC_TOOLCHAIN"
    printf 'POWERPC_TOOLCHAIN_COMPILER=%s\n' \
        "${POWERPC_TOOLCHAIN_COMPILER:-clang}"
    printf 'POWERPC_TOOLCHAIN_SOURCE_MODE=%s\n' \
        "${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
    printf 'POWERPC_TOOLCHAIN_DIR=%s\n' "$POWERPC_TOOLCHAIN_DIR"
    printf 'CONFIG_MAC_NEWWORLD=%s\n' "${CONFIG_MAC_NEWWORLD:-y}"
    printf 'CONFIG_MAC_OLDWORLD=%s\n' "${CONFIG_MAC_OLDWORLD:-y}"
    printf 'WHP_PPC_DEVICE_CONFIG_SIGNATURE=%s\n' "$WHP_PPC_DEVICE_CONFIG_SIGNATURE"
    printf 'CONFIGURE_ARG=%s\n' "${configure_args[*]}"
} > "$config_candidate"

if [[ ! -f "$BUILD_DIR/build.ninja" ]] ||
   [[ ! -f "$config_file" ]] ||
   ! cmp -s "$config_candidate" "$config_file"; then
    if [[ "$ppc_custom_devices" == 1 ]]; then
        ppc_generated_config="$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak"
        ppc_generated_temp="$ppc_generated_config.tmp.$$"
        if [[ ! -w "$(dirname "$ppc_generated_config")" ]]; then
            printf '%s\n' \
                'error: custom PPC machine filtering requires a temporary QEMU device preset,' \
                'but the source configs directory is read-only. The tracked PPC defaults remain buildable.' >&2
            rm -f "$config_candidate"
            return 1
        fi
        awk '
            !/^CONFIG_MAC_NEWWORLD=/ && !/^CONFIG_MAC_OLDWORLD=/ { print }
        ' "$SOURCE_DIR/configs/devices/ppc-softmmu/default.mak" > "$ppc_generated_temp"
        {
            printf '\n# WHP temporary user overrides; removed after configure.\n'
            printf 'CONFIG_MAC_NEWWORLD=%s\n' "${CONFIG_MAC_NEWWORLD:-y}"
            printf 'CONFIG_MAC_OLDWORLD=%s\n' "${CONFIG_MAC_OLDWORLD:-y}"
        } >> "$ppc_generated_temp"
        mv "$ppc_generated_temp" "$ppc_generated_config"
    fi

    (
        cd "$BUILD_DIR"
        "$SOURCE_DIR/configure" "${configure_args[@]}"
    ) || configure_status=$?

    if [[ -n "$ppc_generated_config" ]]; then
        rm -f "$ppc_generated_config" "$ppc_generated_temp"
    fi
    if [[ "$configure_status" != 0 ]]; then
        rm -f "$config_candidate"
        return "$configure_status"
    fi
    mv "$config_candidate" "$config_file"
else
    rm -f "$config_candidate"
fi
}
