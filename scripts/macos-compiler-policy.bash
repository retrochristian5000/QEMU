#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: macOS compiler policy requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi

if [[ "${WHP_MACOS_COMPILER_POLICY_APPLIED:-0}" == "1" ]]; then
    return 0 2>/dev/null || exit 0
fi

MACOS_ALLOW_NONCLANG="${MACOS_ALLOW_NONCLANG:-0}"
case "$MACOS_ALLOW_NONCLANG" in
    0|1) ;;
    *)
        printf 'error: MACOS_ALLOW_NONCLANG must be 0 or 1\n' >&2
        return 1 2>/dev/null || exit 1
        ;;
esac

for required in xcrun basename sed uname; do
    if ! command -v "$required" >/dev/null 2>&1; then
        printf 'error: macOS compiler policy dependency not found: %s\n' \
            "$required" >&2
        return 1 2>/dev/null || exit 1
    fi
done

set_compiler_command()
{
    local command_string="$1"

    case "$command_string" in
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>')
            printf 'error: invalid compiler command: %s\n' "$command_string" >&2
            return 1
            ;;
    esac

    COMPILER_COMMAND=()
    read -r -a COMPILER_COMMAND <<< "$command_string"
    if [[ "${#COMPILER_COMMAND[@]}" -eq 0 ]] ||
       ! command -v "${COMPILER_COMMAND[0]}" >/dev/null 2>&1; then
        printf 'error: compiler command is not executable: %s\n' \
            "$command_string" >&2
        return 1
    fi
}

compiler_family()
{
    local command_string="$1"
    local version

    set_compiler_command "$command_string" || return 1
    version="$("${COMPILER_COMMAND[@]}" --version 2>&1 | sed -n '1p')"
    case "$version" in
        *clang*|*Clang*) printf 'clang\n' ;;
        *GCC*|*gcc*|*'Free Software Foundation'*) printf 'gcc\n' ;;
        *) printf 'unknown\n' ;;
    esac
}

compiler_target_triple()
{
    local command_string="$1"
    local triple=''

    set_compiler_command "$command_string" || return 1
    triple="$("${COMPILER_COMMAND[@]}" -print-target-triple 2>/dev/null || true)"
    if [[ -z "$triple" ]]; then
        triple="$("${COMPILER_COMMAND[@]}" -dumpmachine 2>/dev/null || true)"
    fi
    [[ -n "$triple" ]] || return 1
    printf '%s\n' "$triple"
}

canonical_macos_arch()
{
    case "$1" in
        arm64|aarch64) printf 'arm64\n' ;;
        x86_64|amd64) printf 'x86_64\n' ;;
        *) return 1 ;;
    esac
}

require_apple_darwin_target()
{
    local label="$1"
    local command_string="$2"
    local triple arch vendor os host_arch target_arch

    triple="$(compiler_target_triple "$command_string")" || {
        printf 'error: could not determine %s target triple: %s\n' \
            "$label" "$command_string" >&2
        return 1
    }

    IFS='-' read -r arch vendor os _ <<< "$triple"
    if [[ "$vendor" != apple ]]; then
        printf '%s\n' \
            "error: $label must use an Apple Darwin/macOS target triple." \
            "compiler: $command_string" \
            "target:   $triple" >&2
        return 1
    fi
    case "$os" in
        darwin*|macos*|macosx*) ;;
        *)
            printf '%s\n' \
                "error: $label must use an Apple Darwin/macOS target triple." \
                "compiler: $command_string" \
                "target:   $triple" >&2
            return 1
            ;;
    esac

    host_arch="$(canonical_macos_arch "$(uname -m)")" || {
        printf 'error: unsupported macOS host architecture: %s\n' "$(uname -m)" >&2
        return 1
    }
    target_arch="$(canonical_macos_arch "$arch")" || {
        printf 'error: unsupported %s target architecture in triple: %s\n' \
            "$label" "$triple" >&2
        return 1
    }
    if [[ "$target_arch" != "$host_arch" ]]; then
        printf '%s\n' \
            "error: $label target architecture does not match the macOS host." \
            "host:     $host_arch" \
            "target:   $triple" >&2
        return 1
    fi

    printf '%s\n' "$triple"
}

APPLE_CLANG="$(xcrun --sdk macosx --find clang)"
APPLE_CLANGXX="$(xcrun --sdk macosx --find clang++)"

cc_was_set=0
cxx_was_set=0
[[ -n "${CC:-}" ]] && cc_was_set=1
[[ -n "${CXX:-}" ]] && cxx_was_set=1

if [[ "$cc_was_set" == "0" && "$cxx_was_set" == "0" ]]; then
    export CC="$APPLE_CLANG"
    export CXX="$APPLE_CLANGXX"
elif [[ "$cc_was_set" != "$cxx_was_set" ]]; then
    printf '%s\n' \
        'error: CC and CXX must be selected as a pair on macOS.' \
        "CC=${CC:-<unset>}" \
        "CXX=${CXX:-<unset>}" \
        'Set both to Apple Clang, or both to matching GNU GCC drivers.' >&2
    return 1 2>/dev/null || exit 1
fi

export OBJC="${OBJC:-$APPLE_CLANG}"
export CC_FOR_BUILD="${CC_FOR_BUILD:-$APPLE_CLANG}"
export CXX_FOR_BUILD="${CXX_FOR_BUILD:-$APPLE_CLANGXX}"
export OBJC_FOR_BUILD="${OBJC_FOR_BUILD:-$APPLE_CLANG}"

cc_family="$(compiler_family "$CC")"
cxx_family="$(compiler_family "$CXX")"
objc_family="$(compiler_family "$OBJC")"
build_cc_family="$(compiler_family "$CC_FOR_BUILD")"
build_cxx_family="$(compiler_family "$CXX_FOR_BUILD")"

if [[ "$cc_family" == unknown || "$cxx_family" == unknown ]]; then
    printf '%s\n' \
        'error: could not identify the macOS QEMU compiler family.' \
        "CC=$CC ($cc_family)" \
        "CXX=$CXX ($cxx_family)" >&2
    return 1 2>/dev/null || exit 1
fi
if [[ "$cc_family" != "$cxx_family" ]]; then
    printf '%s\n' \
        'error: mixed C and C++ compiler families are not supported.' \
        "CC=$CC ($cc_family)" \
        "CXX=$CXX ($cxx_family)" >&2
    return 1 2>/dev/null || exit 1
fi

if [[ "$objc_family" != clang ]]; then
    printf '%s\n' \
        'error: the macOS Cocoa frontend must use Apple Clang.' \
        "OBJC=$OBJC ($objc_family)" \
        'GNU GCC may be selected for CC/CXX only with MACOS_ALLOW_NONCLANG=1.' >&2
    return 1 2>/dev/null || exit 1
fi

if [[ "$build_cc_family" != clang || "$build_cxx_family" != clang ]]; then
    printf '%s\n' \
        'error: QEMU build-machine tools must use Apple Clang on macOS.' \
        "CC_FOR_BUILD=$CC_FOR_BUILD ($build_cc_family)" \
        "CXX_FOR_BUILD=$CXX_FOR_BUILD ($build_cxx_family)" \
        'Use TOOLCHAIN_HOST_CC/TOOLCHAIN_HOST_CXX to experiment with GNU GCC' \
        'only inside the PowerPC cross-toolchain bootstrap.' >&2
    return 1 2>/dev/null || exit 1
fi

MACOS_CC_TARGET_TRIPLE="$(require_apple_darwin_target CC "$CC")" || \
    return 1 2>/dev/null || exit 1
MACOS_CXX_TARGET_TRIPLE="$(require_apple_darwin_target CXX "$CXX")" || \
    return 1 2>/dev/null || exit 1
MACOS_OBJC_TARGET_TRIPLE="$(require_apple_darwin_target OBJC "$OBJC")" || \
    return 1 2>/dev/null || exit 1
MACOS_BUILD_CC_TARGET_TRIPLE="$(require_apple_darwin_target CC_FOR_BUILD "$CC_FOR_BUILD")" || \
    return 1 2>/dev/null || exit 1
MACOS_BUILD_CXX_TARGET_TRIPLE="$(require_apple_darwin_target CXX_FOR_BUILD "$CXX_FOR_BUILD")" || \
    return 1 2>/dev/null || exit 1
export MACOS_CC_TARGET_TRIPLE MACOS_CXX_TARGET_TRIPLE MACOS_OBJC_TARGET_TRIPLE
export MACOS_BUILD_CC_TARGET_TRIPLE MACOS_BUILD_CXX_TARGET_TRIPLE

case "$cc_family" in
    clang)
        MACOS_EFFECTIVE_COMPILER_FAMILY=clang
        ;;
    gcc)
        if [[ "$MACOS_ALLOW_NONCLANG" != "1" ]]; then
            printf '%s\n' \
                'error: GNU GCC was selected for the QEMU macOS host build.' \
                'Apple Clang is the supported default for Cocoa and Apple SDK integration.' \
                'Set MACOS_ALLOW_NONCLANG=1 only for an intentional experiment.' >&2
            return 1 2>/dev/null || exit 1
        fi

        # Native Apple Silicon defaults to Clang LTO.  GNU GCC uses a
        # different linker-plugin and archive-tool contract, so never inherit
        # that default into the experimental GCC path.
        if [[ "${QEMU_HOST_LTO:-0}" == "1" ]]; then
            printf '%s\n' \
                'warning: disabling QEMU_HOST_LTO for the GNU GCC macOS path.' \
                'GCC LTO requires a separate plugin-aware ar/nm/linker policy.' >&2
        fi
        export QEMU_HOST_LTO=0
        MACOS_EFFECTIVE_COMPILER_FAMILY=gcc
        ;;
esac

export MACOS_EFFECTIVE_COMPILER_FAMILY
export WHP_MACOS_COMPILER_POLICY_APPLIED=1

printf '%s\n' \
    "QEMU C compiler:          $CC ($cc_family; $MACOS_CC_TARGET_TRIPLE)" \
    "QEMU C++ compiler:        $CXX ($cxx_family; $MACOS_CXX_TARGET_TRIPLE)" \
    "QEMU Objective-C:         $OBJC ($objc_family; $MACOS_OBJC_TARGET_TRIPLE)" \
    "build-machine compiler:   $CC_FOR_BUILD/$CXX_FOR_BUILD" \
    "QEMU host LTO:            ${QEMU_HOST_LTO:-automatic}"