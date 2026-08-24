#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
SOURCE_DIR="$(cd -- "$SCRIPT_DIR/.." && pwd)"

# build.sh is the only public policy entry point.  A direct invocation of this
# implementation must re-enter through it rather than recreating shell policy.
if [[ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]]; then
    exec "$SOURCE_DIR/build.sh" "$@"
fi
: "${WHP_BUILD_BASH:?WHP_BUILD_BASH is required}"

source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SCRIPT_DIR/macos-build-hygiene.bash"

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

if [[ "$(uname -s)" != Darwin ]]; then
    printf 'error: scripts/macos-builder.bash must run on macOS\n' >&2
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
export MACOS_SDK_VERSION="$(xcrun --sdk "$SDKROOT" --show-sdk-version)"
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
if [[ "$process_arch" == arm64 ]] &&
   ! version_is_at_most 11.0 "$MACOSX_DEPLOYMENT_TARGET"; then
    printf '%s\n' \
        'error: arm64 macOS builds require deployment target 11.0 or newer.' \
        "selected: $MACOSX_DEPLOYMENT_TARGET" >&2
    exit 1
fi

source "$SCRIPT_DIR/macos-compiler-policy.bash"

reject_managed_flags
for variable in CFLAGS CXXFLAGS OBJCFLAGS LDFLAGS; do
    whp_append_flag "$variable" "-isysroot $SDKROOT"
    whp_append_flag "$variable" "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
done

# Apple ld applies only its essential optimization set by default.  Use the
# release linker optimization pass and remove unreachable code/data from QEMU
# host binaries.  Keep this on the supported Apple Clang path so experimental
# GNU GCC builds retain their separate linker policy.
if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
    whp_append_flag LDFLAGS "-Wl,-O2"
    whp_append_flag LDFLAGS "-Wl,-dead_strip"
fi

CONFIG_SHELL="$WHP_BUILD_BASH"
export CONFIG_SHELL

prepare_macos_build_tree

printf '%s\n' \
    "macOS SDK:               $SDKROOT" \
    "macOS SDK version:       $MACOS_SDK_VERSION" \
    "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET" \
    "compiler family:         $MACOS_EFFECTIVE_COMPILER_FAMILY" \
    "WHP build shell:         $WHP_BUILD_BASH" \
    "QEMU build directory:    $BUILD_DIR" \
    "firmware tools:          $OPENBIOS_TOOLS_DIR" \
    "OpenBIOS build owner:    Meson/Ninja"

exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
