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

if [[ "$(uname -s)" != "Darwin" ]]; then
    printf 'error: scripts/macos-builder.sh must run on macOS\n' >&2
    exit 1
fi

for required in xcrun xcode-select sw_vers awk; do
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

printf '%s\n' \
    "macOS SDK:               $SDKROOT" \
    "macOS SDK version:       $MACOS_SDK_VERSION" \
    "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET" \
    "compiler family:         $MACOS_EFFECTIVE_COMPILER_FAMILY" \
    "WHP build shell:         $WHP_BUILD_BASH" \
    "configure shell:         $CONFIG_SHELL"

exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
