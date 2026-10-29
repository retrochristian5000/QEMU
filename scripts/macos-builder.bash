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

# Translate user-provided -threads spellings into canonical -Wl,--threads
# options. This works even with a pre-driver-fix Clang, but only when the
# selected Mach-O LLD passes an actual link probe. Never forward to Apple ld.
normalize_macho_thread_flags()
{
    local arg previous='' changed=0
    local -a ld_args=() normalized=()
    read -r -a ld_args <<< "${LDFLAGS:-}"
    for arg in "${ld_args[@]}"; do
        case "$arg" in
            -threads|--threads|-threads=*|--threads=*)
                if [[ "$previous" == -Xlinker ]]; then
                    printf 'error: unsupported Mach-O linker thread flag after -Xlinker: %s\n' "$arg" >&2
                    return 1
                fi
                if [[ "$arg" == *=* ]]; then
                    normalized+=("-Wl,--threads=${arg#*=}")
                else
                    normalized+=("-Wl,--threads")
                fi
                changed=1
                ;;
            *) normalized+=("$arg") ;;
        esac
        previous="$arg"
    done
    if (( changed )); then
        LDFLAGS="${normalized[*]}"
        export LDFLAGS
    fi
}

# Probe the exact selected Mach-O linker instead of relying on names alone.
whp_native_lld_accepts_threads()
{
    local flag="$1"
    local -a probe_cc=()
    read -r -a probe_cc <<< "${CC:-clang}"
    [[ "${#probe_cc[@]}" -gt 0 ]] || return 1

    printf 'int main(void) { return 0; }\n' |
        "${probe_cc[@]}" -arch "$WHP_MACOS_ARCH" \
            -isysroot "$SDKROOT" \
            "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
            -fuse-ld=lld "$flag" -x c - -o /dev/null >/dev/null 2>&1
}

validate_macho_thread_flags()
{
    local arg
    local -a ld_args=()
    read -r -a ld_args <<< "${LDFLAGS:-}"
    for arg in "${ld_args[@]}"; do
        case "$arg" in
            -Wl,-threads|-Wl,-threads=*|-Wl,--threads|-Wl,--threads=*)
                if [[ "${NATIVE_LLVM_LDFLAG:-}" == -fuse-ld=lld && \
                      -n "${NATIVE_LLVM_DIR:-}" && \
                      "${LD:-}" == "$NATIVE_LLVM_DIR/bin/ld64.lld" ]] && \
                   whp_native_lld_accepts_threads "$arg"; then
                    continue
                fi
                printf '%s\n' \
                    "error: selected Mach-O linker does not accept $arg" \
                    'Use the WHP LLVM ld64.lld with -Wl,--threads[=N], or omit this optional flag.' >&2
                exit 1
                ;;
            -Wl,-threads,*|-Wl,--threads,*|-Xlinker=-threads|-Xlinker=--threads)
                printf '%s\n' \
                    "error: unsupported Mach-O linker thread flag in LDFLAGS: $arg" \
                    'Use one complete -Wl,--threads[=N] argument; comma-separated values are invalid.' >&2
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

# build.sh has already staged and verified the private SDL3 shared library.
# The hygiene step above discards all inherited search paths, including those
# populated by the WHP SDL bootstrap. Restore only this validated, managed
# prefix after sanitizing; do not reopen arbitrary user-supplied search paths.
if [[ -n "${WHP_SDL_PREFIX:-}" &&
      -f "$WHP_SDL_PREFIX/lib/pkgconfig/sdl3.pc" ]]; then
    whp_append_colon_path PKG_CONFIG_PATH "$WHP_SDL_PREFIX/lib/pkgconfig"
    whp_append_colon_path CMAKE_PREFIX_PATH "$WHP_SDL_PREFIX"
    # Do not restore DYLD_FALLBACK_LIBRARY_PATH for the QEMU host build:
    # dyld may ignore DYLD_* overrides for protected processes, and the
    # shipped executable must load SDL from its embedded @loader_path rpaths.
    # Keeping the fallback here could mask broken LC_RPATH commands in CI.
fi

for required in xcrun xcode-select sw_vers awk grep sed mktemp dirname \
    basename mv ls; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: required Apple build tool is missing: %s\n' "$required" >&2
        exit 1
    fi
done

# Normalize DEVELOPER_DIR (including Xcode.app) ahead of SDK selection.
source "$SCRIPT_DIR/whp-build/macos-developer-tools.sh"
apple_developer_dir="$(whp_apple_developer_root)" || exit 1
export DEVELOPER_DIR="$apple_developer_dir"
selected_apple_sdk="$(whp_apple_find_sdk)" || exit 1
if [[ -n "${SDKROOT:-}" ]]; then
    # An explicit older macOS SDK is supported inside this developer root,
    # but never pair Xcode's compiler with CLT's SDK or vice versa.
    whp_apple_check_sdkroot "$SDKROOT" || exit 1
else
    SDKROOT="$selected_apple_sdk"
fi
export SDKROOT
apple_developer_kind="$(whp_apple_developer_kind "$DEVELOPER_DIR")"
unset apple_developer_dir selected_apple_sdk
# CMAKE_OSX_SYSROOT accepts iPhoneOS and iPhoneSimulator SDKs too. A native
# QEMU/LLVM host bootstrap must never inherit one from an iPad/iOS build.
sdk_real_path="$(cd "$SDKROOT" && pwd -P)" || exit 1
case "${sdk_real_path##*/}" in
    MacOSX*.sdk) ;;
    *)
        printf 'error: macOS host build requires a MacOSX.sdk; got: %s\n' "$SDKROOT" >&2
        exit 1
        ;;
esac
unset sdk_real_path
export MACOS_SDK_VERSION="$(xcrun --sdk "$SDKROOT" --show-sdk-version)"
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

# Keep explicit archive-tool choices authoritative.  When the selected Clang
# has a complete LLVM archive trio beside it, prefer that coherent family.
# This covers managed LLVM and standalone LLVM installations without making
# llvm-ar a platform-wide requirement.  If any sibling is missing, retain the
# normal PATH-independent Apple tools rather than constructing a mixed family.
if [[ -z "${AR:-}" && -z "${RANLIB:-}" && -z "${NM:-}" &&
      "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
    llvm_ar="$(whp_compiler_sibling_tool "$CC" llvm-ar || true)"
    llvm_ranlib="$(whp_compiler_sibling_tool "$CC" llvm-ranlib || true)"
    llvm_nm="$(whp_compiler_sibling_tool "$CC" llvm-nm || true)"
    if [[ -n "$llvm_ar" && -n "$llvm_ranlib" && -n "$llvm_nm" ]]; then
        AR="$llvm_ar"
        RANLIB="$llvm_ranlib"
        NM="$llvm_nm"
    fi
    unset llvm_ar llvm_ranlib llvm_nm
fi

export AR="${AR:-/usr/bin/ar}"
export RANLIB="${RANLIB:-/usr/bin/ranlib}"
export NM="${NM:-/usr/bin/nm}"
export STRIP="${STRIP:-/usr/bin/strip}"
export LIPO="${LIPO:-/usr/bin/lipo}"

reject_managed_flags
WHP_MACOS_ARCH="$(whp_select_macos_arch "$CC" "$SDKROOT" \
    "$MACOSX_DEPLOYMENT_TARGET" "$process_arch" "$CXX")" || exit 1
export WHP_MACOS_ARCH

# The selected CPU subtype does not prevent Clang++ from compiling unsigned
# C++ virtual calls when an inherited flag disables pointer authentication.
# Validate user/compiler sources before mutating any managed compile flags.
whp_macos_audit_arm64e_codegen_flags || exit 1

# The directory name guards SDK family selection; these native header macros
# also reject mislabeled SDK content before CMake creates an invalid cache.
sdk_probe_arch=()
if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
    sdk_probe_arch=(-arch "$WHP_MACOS_ARCH")
fi
if ! "$CC" "${sdk_probe_arch[@]}" -isysroot "$SDKROOT" \
        "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
        -x c -fsyntax-only - <<'WHP_MACOS_HOST_SDK'
#include <TargetConditionals.h>
#if !defined(TARGET_OS_OSX) || !TARGET_OS_OSX || \
    (defined(TARGET_OS_IOS) && TARGET_OS_IOS) || \
    (defined(TARGET_OS_MACCATALYST) && TARGET_OS_MACCATALYST) || \
    (defined(TARGET_OS_SIMULATOR) && TARGET_OS_SIMULATOR)
#error The selected SDK must provide native macOS host headers
#endif
WHP_MACOS_HOST_SDK
then
    printf 'error: macOS host SDK header probe failed: %s\n' "$SDKROOT" >&2
    exit 1
fi
if ! "$CXX" "${sdk_probe_arch[@]}" -isysroot "$SDKROOT" \
        "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
        -std=c++17 -x c++ -fsyntax-only - <<'WHP_MACOS_HOST_CXX_SDK'
#include <TargetConditionals.h>
#include <memory>
#if !defined(TARGET_OS_OSX) || !TARGET_OS_OSX || \
    (defined(TARGET_OS_IOS) && TARGET_OS_IOS) || \
    (defined(TARGET_OS_MACCATALYST) && TARGET_OS_MACCATALYST) || \
    (defined(TARGET_OS_SIMULATOR) && TARGET_OS_SIMULATOR)
#error The selected C++ SDK must provide native macOS headers
#endif
WHP_MACOS_HOST_CXX_SDK
then
    printf 'error: macOS host C++ SDK/libc++ probe failed: %s\n' "$SDKROOT" >&2
    exit 1
fi
unset sdk_probe_arch

# The linker selection must agree across both Clang drivers and all active
# user flag sources.  A successful C-only probe must not hide a C++ override.
if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
    whp_macos_audit_linker_driver_flags || exit 1
fi

# UBSan may be enabled for QEMU while native LLVM still owns an arm64-only
# compiler-rt distribution. Automatic builds remain arm64; an explicit
# arm64e request must have the matching UBSan dylib before expensive work.
case "${QEMU_UBSAN:-0}:$WHP_MACOS_ARCH" in
    1:arm64e|y:arm64e)
        whp_macos_verify_ubsan_abi "$CC" "$LIPO" "$WHP_MACOS_ARCH" || exit 1
        ;;
esac

# A user-selected ARM64e+ASan QEMU build needs more than a working C++ link.
# Fail early if dyld cannot load the matching compiler-rt or if the ASan
# runtime fails to diagnose a real heap overflow under authenticated calls.
# The ordinary arm64 ASan and non-sanitized arm64e lanes are unchanged.
case "${QEMU_ASAN:-0}:$WHP_MACOS_ARCH" in
    1:arm64e|y:arm64e)
        if [[ -n "${NATIVE_LLVM_LDFLAG:-}" ]]; then
            printf 'error: ARM64e ASan runtime admission requires Apple ld\n' >&2
            exit 1
        fi
        "${PYTHON:-python3}" "$SOURCE_DIR/scripts/verify-native-asan-darwin.py" \
            --clang "$CC" --clangxx "$CXX" --arch arm64e \
            --sdkroot "$SDKROOT" \
            --deployment-target "$MACOSX_DEPLOYMENT_TARGET" \
            --runtime-only || exit 1
        ;;
esac

for variable in CFLAGS CXXFLAGS OBJCFLAGS LDFLAGS; do
    if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
        whp_append_flag "$variable" "-arch $WHP_MACOS_ARCH"
    fi
    whp_append_flag "$variable" "-isysroot $SDKROOT"
    whp_append_flag "$variable" "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET"
done

normalize_macho_thread_flags
validate_macho_thread_flags

# Mach-O LLD's --read-workers is an optional performance extension. It
# appeared after some of the LLVM versions supported by this fork and can be
# rejected by a linker built without threading. Probe it through the actual
# Clang driver before adding it to the host's LDFLAGS; --help alone does not
# prove that the option works for this binary. Never pass it to Apple ld.
whp_native_lld_accepts_read_workers()
{
    local workers="$1"
    local driver_var language
    local -a probe_driver=()

    # LDFLAGS are shared by both Clang and Clang++. The C-only driver can
    # accept --read-workers even when the C++ driver uses a different wrapper
    # or forwards the option to a different linker.
    for driver_var in CC CXX; do
        probe_driver=()
        read -r -a probe_driver <<< "${!driver_var:-}"
        [[ "${#probe_driver[@]}" -gt 0 ]] || return 1
        if [[ "$driver_var" == CXX ]]; then
            language=c++
        else
            language=c
        fi

        if ! printf 'int main(void) { return 0; }\n' |
            "${probe_driver[@]}" -arch "$WHP_MACOS_ARCH" \
                -isysroot "$SDKROOT" \
                "-mmacosx-version-min=$MACOSX_DEPLOYMENT_TARGET" \
                -fuse-ld=lld "-Wl,--read-workers=$workers" \
                -x "$language" - -o /dev/null >/dev/null 2>&1; then
            return 1
        fi
    done
    return 0
}

native_macho_lld=0
if [[ "${NATIVE_LLVM_LDFLAG:-}" == -fuse-ld=lld &&
      -n "${NATIVE_LLVM_DIR:-}" &&
      "${LD:-}" == "$NATIVE_LLVM_DIR/bin/ld64.lld" ]]; then
    native_macho_lld=1
    native_lld_read_workers="${NATIVE_LLVM_READ_WORKERS:-${JOBS:-1}}"
    case "$native_lld_read_workers" in
        ''|*[!0-9]*)
            printf 'error: NATIVE_LLVM_READ_WORKERS must be a non-negative integer: %s\n' \
                "$native_lld_read_workers" >&2
            exit 1
            ;;
    esac
    # Zero is opt-out: omit the argument entirely, even on new LLD versions.
    if [[ "$native_lld_read_workers" != 0 ]]; then
        if whp_native_lld_accepts_read_workers "$native_lld_read_workers"; then
            whp_append_flag LDFLAGS "-Wl,--read-workers=$native_lld_read_workers"
        elif [[ -n "${NATIVE_LLVM_READ_WORKERS+x}" ]]; then
            printf 'error: selected ld64.lld does not accept --read-workers=%s\n' \
                "$native_lld_read_workers" >&2
            exit 1
        else
            printf 'warning: selected ld64.lld cannot use --read-workers; omitting optional link prefetch\n' >&2
        fi
    fi

    # This pinned Mach-O LLD does not yet implement class-selector stubs.
    whp_append_flag OBJCFLAGS "-fno-objc-msgsend-class-selector-stubs"
fi

# -dead_strip works with both Apple ld and Mach-O LLD. The Mach-O LLD -O
# option describes output size, not Apple's release-linker optimization pass.
# Keep Apple-specific -O2 off the LLVM linker command line.
if [[ "$MACOS_EFFECTIVE_COMPILER_FAMILY" == clang ]]; then
    if [[ "$native_macho_lld" == 0 ]]; then
        # This flag is Apple-ld-specific; explicit LLD/mold selections are
        # capability-probed later and must not inherit Apple ld optimizations.
        case "${QEMU_HOST_LINKER:-auto}" in
            lld|mold) ;;
            *) whp_append_flag LDFLAGS "-Wl,-O2" ;;
        esac
    fi
    whp_append_flag LDFLAGS "-Wl,-dead_strip"
fi

CONFIG_SHELL="$WHP_BUILD_BASH"
export CONFIG_SHELL

prepare_macos_build_tree

printf '%s\n' \
    "macOS developer source:  $apple_developer_kind ($DEVELOPER_DIR)" \
    "macOS SDK:               $SDKROOT" \
    "macOS SDK version:       $MACOS_SDK_VERSION" \
    "macOS SDK target range:  ${sdk_minimum_deployment_target:-unknown}..$sdk_maximum_deployment_target" \
    "macOS SDK default target: $sdk_default_deployment_target" \
    "macOS deployment target: $MACOSX_DEPLOYMENT_TARGET ($deployment_target_source)" \
    "macOS Mach-O arch:       $WHP_MACOS_ARCH" \
    "compiler family:         $MACOS_EFFECTIVE_COMPILER_FAMILY" \
    "QEMU archiver:           $AR" \
    "QEMU archive indexer:    $RANLIB" \
    "QEMU symbol reader:      $NM" \
    "WHP build shell:         $WHP_BUILD_BASH" \
    "QEMU build directory:    $BUILD_DIR" \
    "firmware tools:          $OPENBIOS_TOOLS_DIR" \
    "OpenBIOS build owner:    Meson/Ninja"

exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
