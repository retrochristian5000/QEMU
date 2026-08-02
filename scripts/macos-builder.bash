#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: scripts/macos-builder.bash requires GNU Bash\n' >&2
    exit 1
fi
case ":${SHELLOPTS:-}:" in
    *:posix:*)
        printf 'error: scripts/macos-builder.bash cannot run in Bash POSIX mode\n' >&2
        exit 1
        ;;
esac

set -euo pipefail

: "${WHP_BUILD_BASH:?WHP_BUILD_BASH is required}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

source "$SCRIPT_DIR/macos-build-hygiene.bash"

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

validate_version()
{
    local value="$1"
    local component
    local components=()

    case "$value" in
        ''|.*|*.|*..*|*[!0-9.]*) return 1 ;;
    esac
    IFS=. read -r -a components <<< "$value"
    if (( ${#components[@]} < 1 || ${#components[@]} > 3 )); then
        return 1
    fi
    for component in "${components[@]}"; do
        [[ -n "$component" ]] || return 1
    done
}

version_is_at_most()
{
    local left="$1"
    local right="$2"
    local index
    local left_parts=()
    local right_parts=()

    IFS=. read -r -a left_parts <<< "$left"
    IFS=. read -r -a right_parts <<< "$right"
    for index in 0 1 2; do
        local left_value="${left_parts[$index]:-0}"
        local right_value="${right_parts[$index]:-0}"
        if (( 10#$left_value < 10#$right_value )); then
            return 0
        fi
        if (( 10#$left_value > 10#$right_value )); then
            return 1
        fi
    done
    return 0
}

reject_managed_flags()
{
    local variable value

    for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        case " $value " in
            *' -isysroot'*|*' --sysroot'*|*' -mmacosx-version-min'*)
                printf '%s\n' \
                    "error: $variable already selects a macOS SDK or deployment target:" \
                    "  $value" \
                    'Use SDKROOT and MACOSX_DEPLOYMENT_TARGET with this wrapper so' \
                    'compile tests, QEMU host objects, and final links use one policy.' >&2
                exit 1
                ;;
        esac
    done
}

write_openbios_meson_config()
{
    local config="$BUILD_DIR/.whp-openbios-meson.env"
    local temporary="$config.new.$$"
    local make_cmd="${MAKE_CMD:-}"
    local jobs="${JOBS:-}"
    local source_mode="${POWERPC_TOOLCHAIN_SOURCE_MODE:-release}"
    local hostcc="${OPENBIOS_HOSTCC:-${CC_FOR_BUILD:-${CC:-cc}}}"
    local hostcxx="${OPENBIOS_HOSTCXX:-${CXX_FOR_BUILD:-${CXX:-c++}}}"
    local hoststrip="${OPENBIOS_HOSTSTRIP:-${STRIP_FOR_BUILD:-$(xcrun --sdk macosx --find strip)}}"

    case "$source_mode" in
        release|git) ;;
        *)
            printf 'error: POWERPC_TOOLCHAIN_SOURCE_MODE must be release or git\n' >&2
            exit 1
            ;;
    esac

    if [[ -z "$make_cmd" ]]; then
        if command -v gmake >/dev/null 2>&1; then
            make_cmd=gmake
        else
            make_cmd=make
        fi
    fi
    if [[ -z "$jobs" ]]; then
        jobs="$(sysctl -n hw.ncpu 2>/dev/null || printf '1')"
    fi

    umask 077
    {
        printf 'OPENBIOS_DIR=%q\n' "${OPENBIOS_DIR:-$SOURCE_DIR/roms/openbios}"
        printf 'OPENBIOS_TOOLS_DIR=%q\n' "$OPENBIOS_TOOLS_DIR"
        printf 'OPENBIOS_HOSTCC=%q\n' "$hostcc"
        printf 'OPENBIOS_HOSTCXX=%q\n' "$hostcxx"
        printf 'OPENBIOS_HOSTSTRIP=%q\n' "$hoststrip"
        printf 'OPENBIOS_TOKE=%q\n' "${OPENBIOS_TOKE:-}"
        printf 'OPENBIOS_CROSS_COMPILE=%q\n' "${OPENBIOS_CROSS_COMPILE:-}"
        printf 'OPENBIOS_FORCE_RECONFIGURE=%q\n' "${OPENBIOS_FORCE_RECONFIGURE:-0}"
        printf 'BOOTSTRAP_POWERPC_TOOLCHAIN=%q\n' "${BOOTSTRAP_POWERPC_TOOLCHAIN:-1}"
        printf 'POWERPC_TOOLCHAIN_FORCE_REBUILD=%q\n' "${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}"
        printf 'POWERPC_TOOLCHAIN_SOURCE_MODE=%q\n' "$source_mode"
        printf 'POWERPC_TOOLCHAIN_DIR=%q\n' "$POWERPC_TOOLCHAIN_DIR"
        printf 'POWERPC_TOOLCHAIN_WORK_DIR=%q\n' "$POWERPC_TOOLCHAIN_WORK_DIR"
        printf 'POWERPC_TOOLCHAIN_DOWNLOAD_DIR=%q\n' "$POWERPC_TOOLCHAIN_DOWNLOAD_DIR"
        printf 'POWERPC_TOOLCHAIN_GIT_OFFLINE=%q\n' "${POWERPC_TOOLCHAIN_GIT_OFFLINE:-0}"
        printf 'POWERPC_BINUTILS_GIT_URL=%q\n' "${POWERPC_BINUTILS_GIT_URL:-https://sourceware.org/git/binutils-gdb.git}"
        printf 'POWERPC_BINUTILS_GIT_REF=%q\n' "${POWERPC_BINUTILS_GIT_REF:-binutils-2_46-branch}"
        printf 'POWERPC_BINUTILS_GIT_COMMIT=%q\n' "${POWERPC_BINUTILS_GIT_COMMIT:-}"
        printf 'POWERPC_GCC_GIT_URL=%q\n' "${POWERPC_GCC_GIT_URL:-https://gcc.gnu.org/git/gcc.git}"
        printf 'POWERPC_GCC_GIT_REF=%q\n' "${POWERPC_GCC_GIT_REF:-releases/gcc-16}"
        printf 'POWERPC_GCC_GIT_COMMIT=%q\n' "${POWERPC_GCC_GIT_COMMIT:-}"
        printf 'CONFIG_SHELL=%q\n' "${CONFIG_SHELL:-$WHP_BUILD_BASH}"
        printf 'PKG_CONFIG_FOR_BUILD=%q\n' "${PKG_CONFIG_FOR_BUILD:-${PKG_CONFIG:-pkg-config}}"
        printf 'MAKE_CMD=%q\n' "$make_cmd"
        printf 'JOBS=%q\n' "$jobs"
    } > "$temporary"
    mv -f "$temporary" "$config"

    # The firmware is now produced by pc-bios/meson.build. Disable the older
    # pre-configure invocation in builder.sh so there is one owner and one
    # build-graph edge for OpenBIOS.
    export BUILD_OPENBIOS=0
}

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'error: scripts/macos-builder.sh must run on macOS\n' >&2
    exit 1
fi

sanitize_macos_build_environment

for required in xcrun xcode-select sw_vers awk grep sed mktemp dirname \
    basename mv ls; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: required Apple build tool is missing: %s\n' "$required" >&2
        exit 1
    fi
done

export DEVELOPER_DIR="${DEVELOPER_DIR:-$(xcode-select -p 2>/dev/null || true)}"
if [[ -z "$DEVELOPER_DIR" || ! -d "$DEVELOPER_DIR" ]]; then
    printf '%s\n' \
        'error: no active Apple developer directory was found.' \
        'Install the Xcode Command Line Tools or select Xcode with xcode-select.' >&2
    exit 1
fi

export SDKROOT="${SDKROOT:-$(xcrun --sdk macosx --show-sdk-path)}"
MACOS_SDK_VERSION="$(xcrun --sdk macosx --show-sdk-version)"
if [[ ! -d "$SDKROOT" ]]; then
    printf 'error: selected macOS SDK does not exist: %s\n' "$SDKROOT" >&2
    exit 1
fi
case "$SDKROOT" in
    *' '*)
        printf '%s\n' \
            "error: the selected macOS SDK path contains spaces: $SDKROOT" \
            'The current QEMU shell probes split compiler flags on whitespace.' \
            'Select an Xcode or Command Line Tools path without spaces.' >&2
        exit 1
        ;;
esac

host_product_version="$(sw_vers -productVersion)"
default_deployment_target="$(printf '%s\n' "$host_product_version" |
    awk -F. '{ print $1 "." ($2 == "" ? 0 : $2) }')"
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-$default_deployment_target}"

if ! validate_version "$MACOSX_DEPLOYMENT_TARGET"; then
    printf 'error: invalid MACOSX_DEPLOYMENT_TARGET: %s\n' \
        "$MACOSX_DEPLOYMENT_TARGET" >&2
    exit 1
fi
if ! validate_version "$MACOS_SDK_VERSION"; then
    printf 'error: xcrun returned an invalid macOS SDK version: %s\n' \
        "$MACOS_SDK_VERSION" >&2
    exit 1
fi
if ! version_is_at_most "$MACOSX_DEPLOYMENT_TARGET" "$MACOS_SDK_VERSION"; then
    printf '%s\n' \
        "error: deployment target $MACOSX_DEPLOYMENT_TARGET is newer than SDK $MACOS_SDK_VERSION." \
        'Select a newer SDK or lower MACOSX_DEPLOYMENT_TARGET.' >&2
    exit 1
fi

process_arch="$(uname -m)"
if [[ "$process_arch" == "arm64" ]] &&
   ! version_is_at_most 11.0 "$MACOSX_DEPLOYMENT_TARGET"; then
    printf '%s\n' \
        "error: arm64 macOS builds require deployment target 11.0 or newer." \
        "selected: $MACOSX_DEPLOYMENT_TARGET" >&2
    exit 1
fi

# Resolve compiler roles before builder.sh computes architecture and LTO
# defaults.  This keeps Clang's Apple integration separate from an explicit
# GNU GCC experiment and prevents mixed C/C++ compiler families.
source "$SCRIPT_DIR/macos-compiler-policy.bash"

reject_managed_flags
for variable in CFLAGS CXXFLAGS OBJCFLAGS LDFLAGS; do
    append_flag "$variable" "-isysroot $SDKROOT"
    append_flag "$variable" "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
done

QEMU_CONFIG_SHELL="${QEMU_CONFIG_SHELL:-$WHP_BUILD_BASH}"
if [[ ! -x "$QEMU_CONFIG_SHELL" ]] ||
   ! "$QEMU_CONFIG_SHELL" --noprofile --norc -c '
        test -n "${BASH_VERSION:-}" || exit 1
        case ":${SHELLOPTS:-}:" in *:posix:*) exit 1 ;; esac
   ' >/dev/null 2>&1; then
    printf '%s\n' \
        "error: QEMU_CONFIG_SHELL must be a non-POSIX GNU Bash: $QEMU_CONFIG_SHELL" \
        'Do not use dash or zsh for GCC/binutils configure recursion.' >&2
    exit 1
fi
export CONFIG_SHELL="$QEMU_CONFIG_SHELL"

prepare_macos_build_tree
write_openbios_meson_config

printf '%s\n' \
    "macOS SDK:               $SDKROOT" \
    "macOS SDK version:       $MACOS_SDK_VERSION" \
    "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET" \
    "compiler family:         $MACOS_EFFECTIVE_COMPILER_FAMILY" \
    "WHP build shell:         $WHP_BUILD_BASH" \
    "configure shell:         $CONFIG_SHELL" \
    "QEMU build directory:    $BUILD_DIR" \
    "firmware tools:          $OPENBIOS_TOOLS_DIR" \
    "OpenBIOS build owner:    Meson/Ninja"

exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
