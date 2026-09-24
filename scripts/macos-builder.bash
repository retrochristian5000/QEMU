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
source "$SCRIPT_DIR/macos-arch-policy.bash"

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

read_sdk_version_setting()
{
    local key="$1"
    local settings_file
    local value

    command -v plutil >/dev/null 2>&1 || return 1
    for settings_file in "$SDKROOT/SDKSettings.json" "$SDKROOT/SDKSettings.plist"; do
        [[ -f "$settings_file" ]] || continue
        value="$(plutil -extract "$key" raw -o - "$settings_file" 2>/dev/null || true)"
        if validate_version "$value"; then
            printf '%s\n' "$value"
            return 0
        fi
    done
    return 1
}

read_macos_sdk_deployment_setting()
{
    local name="$1"
    local value

    value="$(read_sdk_version_setting "SupportedTargets.macosx.$name" || true)"
    if [[ -z "$value" ]]; then
        value="$(read_sdk_version_setting "$name" || true)"
    fi
    [[ -n "$value" ]] || return 1
    printf '%s\n' "$value"
}

sdk_release_ceiling()
{
    local version="$1"
    local parts=()

    IFS=. read -r -a parts <<< "$version"
    printf '%s.%s.99\n' "${parts[0]}" "${parts[1]:-0}"
}

reject_managed_flags()
{
    local variable value

    for variable in CFLAGS CXXFLAGS OBJCFLAGS CPPFLAGS LDFLAGS; do
        value="${!variable:-}"
        case " $value " in
            *' -isysroot'*|*' --sysroot'*|*' -mmacosx-version-min'*|*' -arch '*)
                printf '%s\n' \
                    "$variable already selects a managed macOS SDK, deployment target, or architecture:" \
                    "  $value" \
                    'Use SDKROOT, MACOSX_DEPLOYMENT_TARGET, and WHP_MACOS_ARCH with this wrapper so' \
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
host_deployment_target="$(printf '%s\n' "$host_product_version" |
    awk -F. '{ print $1 "." ($2 == "" ? 0 : $2) }')"

if ! validate_version "$MACOS_SDK_VERSION"; then
    printf 'error: xcrun returned an invalid macOS SDK version: %s\n' \
        "$MACOS_SDK_VERSION" >&2
    exit 1
fi

sdk_default_deployment_target="$(
    read_macos_sdk_deployment_setting DefaultDeploymentTarget || true
)"
sdk_minimum_deployment_target="$(
    read_macos_sdk_deployment_setting MinimumDeploymentTarget || true
)"
sdk_maximum_deployment_target="$(
    read_macos_sdk_deployment_setting MaximumDeploymentTarget || true
)"

# SDK Version identifies headers/APIs, while deployment metadata identifies
# which runtime versions the SDK can target. Older SDKs may be selected on a
# newer host, and beta/newer SDKs may be selected on an older host. Keep the
# automatic runtime target on the host when possible, but clamp it to the SDK's
# own default if the host lies above the SDK's supported range.
if [[ -z "$sdk_default_deployment_target" ]]; then
    sdk_default_deployment_target="$MACOS_SDK_VERSION"
fi
if [[ -z "$sdk_maximum_deployment_target" ]]; then
    sdk_maximum_deployment_target="$(sdk_release_ceiling "$MACOS_SDK_VERSION")"
fi

if [[ -n "${MACOSX_DEPLOYMENT_TARGET:-}" ]]; then
    deployment_target_source=user
else
    deployment_target_source=host
    MACOSX_DEPLOYMENT_TARGET="$host_deployment_target"
    if ! version_is_at_most "$MACOSX_DEPLOYMENT_TARGET" \
        "$sdk_maximum_deployment_target"; then
        MACOSX_DEPLOYMENT_TARGET="$sdk_default_deployment_target"
        deployment_target_source=sdk-default
    fi
fi
export MACOSX_DEPLOYMENT_TARGET
export MACOS_SDK_DEFAULT_DEPLOYMENT_TARGET="$sdk_default_deployment_target"
export MACOS_SDK_MINIMUM_DEPLOYMENT_TARGET="$sdk_minimum_deployment_target"
export MACOS_SDK_MAXIMUM_DEPLOYMENT_TARGET="$sdk_maximum_deployment_target"

if ! validate_version "$MACOSX_DEPLOYMENT_TARGET"; then
    printf 'error: invalid MACOSX_DEPLOYMENT_TARGET: %s\n' \
        "$MACOSX_DEPLOYMENT_TARGET" >&2
    exit 1
fi
if [[ -n "$sdk_minimum_deployment_target" ]] &&
   ! version_is_at_most "$sdk_minimum_deployment_target" \
       "$MACOSX_DEPLOYMENT_TARGET"; then
    printf '%s\n' \
        "error: deployment target $MACOSX_DEPLOYMENT_TARGET is older than the selected SDK minimum $sdk_minimum_deployment_target." \
        'Select an older SDK or raise MACOSX_DEPLOYMENT_TARGET.' >&2
    exit 1
fi
if ! version_is_at_most "$MACOSX_DEPLOYMENT_TARGET" \
    "$sdk_maximum_deployment_target"; then
    printf '%s\n' \
        "error: deployment target $MACOSX_DEPLOYMENT_TARGET is newer than the selected SDK maximum $sdk_maximum_deployment_target." \
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

# Keep Darwin's PATH-independent Apple binary tools as the fallback, but do
# not overwrite an explicit tool family selected by build.sh.  In particular,
# BOOTSTRAP_NATIVE_LLVM carries llvm-ar/llvm-nm/llvm-strip/llvm-lipo plus the
# LLVM object readers through the build so one LLVM revision owns the host
# binary pipeline instead of drifting back to ambient PATH tools.
export AR="${AR:-/usr/bin/ar}"
export NM="${NM:-/usr/bin/nm}"
export RANLIB="${RANLIB:-/usr/bin/ranlib}"
export STRIP="${STRIP:-/usr/bin/strip}"
export LIPO="${LIPO:-/usr/bin/lipo}"

reject_managed_flags
WHP_MACOS_ARCH="$(whp_select_macos_arch "$CC" "$SDKROOT" \
    "$MACOSX_DEPLOYMENT_TARGET" "$process_arch")" || exit 1
export WHP_MACOS_ARCH

for variable in CFLAGS CXXFLAGS OBJCFLAGS LDFLAGS; do
    if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
        whp_append_flag "$variable" "-arch $WHP_MACOS_ARCH"
    fi
    whp_append_flag "$variable" "-isysroot $SDKROOT"
    whp_append_flag "$variable" "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
done

# Clang can lower known class messages to linker-synthesized symbols such as
# _objc_msgSendClass$new$_OBJC_CLASS_$_NSTextField.  The pinned WHP ld64.lld
# currently synthesizes the older _objc_msgSend$selector form only.  Keep that
# optimization available, but force class sends back to the supported form for
# this exact native LLVM linker/compiler pairing.  Apple's ld remains free to
# use the newer class-selector stubs.
#
# Mach-O LLD also leaves eager input prefetching disabled by default.  Reuse the
# build's established parallelism as the default page-in worker count so QEMU's
# large object/archive set can be faulted in concurrently with linker work.
# Keep this LLD-specific flag inside the same exact toolchain guard; callers can
# set NATIVE_LLVM_READ_WORKERS=0 to disable it or choose another non-negative
# worker count without exposing --read-workers to Apple's system linker.
if [[ "${NATIVE_LLVM_LDFLAG:-}" == -fuse-ld=lld &&
      -n "${NATIVE_LLVM_DIR:-}" &&
      "${LD:-}" == "$NATIVE_LLVM_DIR/bin/ld64.lld" ]]; then
    native_lld_read_workers="${NATIVE_LLVM_READ_WORKERS:-${JOBS:-1}}"
    case "$native_lld_read_workers" in
        ''|*[!0-9]*)
            printf 'error: NATIVE_LLVM_READ_WORKERS must be a non-negative integer: %s\n' \
                "$native_lld_read_workers" >&2
            exit 1
            ;;
    esac
    whp_append_flag LDFLAGS "-Wl,--read-workers=$native_lld_read_workers"
    whp_append_flag OBJCFLAGS "-fno-objc-msgsend-class-selector-stubs"
fi

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
    "macOS SDK target range:  ${sdk_minimum_deployment_target:-unknown}..$sdk_maximum_deployment_target" \
    "macOS SDK default target: $sdk_default_deployment_target" \
    "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET ($deployment_target_source)" \
    "macOS Mach-O arch:       $WHP_MACOS_ARCH" \
    "compiler family:         $MACOS_EFFECTIVE_COMPILER_FAMILY" \
    "WHP build shell:         $WHP_BUILD_BASH" \
    "QEMU build directory:    $BUILD_DIR" \
    "firmware tools:          $OPENBIOS_TOOLS_DIR" \
    "OpenBIOS build owner:    Meson/Ninja"

exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
