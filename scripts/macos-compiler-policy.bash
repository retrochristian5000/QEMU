#!/usr/bin/env bash

if [[ -z "${BASH_VERSION:-}" ]]; then
    printf 'error: macOS compiler policy requires GNU Bash\n' >&2
    return 1 2>/dev/null || exit 1
fi

if [[ "${WHP_MACOS_COMPILER_POLICY_APPLIED:-0}" == "1" ]]; then
    return 0 2>/dev/null || exit 0
fi

# Use the shared Darwin-family syntax checker without assuming all Darwin
# implementations use Apple's vendor name. The Apple SDK, linker, runtime and
# effective ABI still require independent native build probes.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/whp-build/macos-target-abi.bash"

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
    local macros verbose

    set_compiler_command "$command_string" || return 1
    # Compiler names, --version banners and __GNUC__ alone do not identify
    # a compiler. For example, Apple's /usr/bin/gcc can invoke Clang.
    # This preprocessor-only probe requires no headers or SDK rewrites.
    if ! macros="$("${COMPILER_COMMAND[@]}" -dM -E -x c - </dev/null 2>/dev/null)"; then
        printf 'unknown\n'
        return 0
    fi
    case "$macros" in
        *'#define __clang__ 1'*) printf 'clang\n'; return 0 ;;
    esac
    # Other compilers also implement GNU extensions. Identify *GNU GCC*
    # only when its frontend signature and verbose compiler identity
    # agree; otherwise retain unknown instead of assuming GCC.
    case "$macros" in
        *'#define __GNUC__ '*)
            verbose="$(LC_ALL=C "${COMPILER_COMMAND[@]}" -v 2>&1)" || {
                printf 'unknown\n'
                return 0
            }
            case "$verbose" in
                *'gcc version '*) printf 'gcc\n' ;;
                *) printf 'unknown\n' ;;
            esac
            ;;
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

require_darwin_target_identity()
{
    local label="$1"
    local command_string="$2"
    local triple arch host_arch target_arch

    triple="$(compiler_target_triple "$command_string")" || {
        printf 'error: could not determine %s target triple: %s\n' \
            "$label" "$command_string" >&2
        return 1
    }

    # The vendor field is meaningful but cannot alone prove (or disprove)
    # compatibility with a Darwin-family ABI. Reject malformed OS fields and
    # foreign target environments without silently rewriting the vendor.
    if ! darwin_target_identity "$triple" >/dev/null; then
        printf '%s\n' \
            "error: $label must use a well-formed Darwin/macOS target triple." \
            "compiler: $command_string" \
            "target:   $triple" >&2
        return 1
    fi
    arch="${triple%%-*}"

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

# Cache only within this policy invocation, by exact command and probe kind.
# No persistent cache or cross-build assumptions about compiler identity.
compiler_probe_count=0
compiler_probe_kinds=()
compiler_probe_commands=()
compiler_probe_values=()

compiler_probe_once()
{
    local destination="$1" kind="$2" role="$3" command_string="$4"
    local i result

    for ((i = 0; i < compiler_probe_count; i++)); do
        if [[ "${compiler_probe_kinds[i]}" == "$kind" &&
              "${compiler_probe_commands[i]}" == "$command_string" ]]; then
            printf -v "$destination" '%s' "${compiler_probe_values[i]}"
            return 0
        fi
    done

    case "$kind" in
        family) result="$(compiler_family "$command_string")" || return 1 ;;
        target) result="$(require_darwin_target_identity "$role" "$command_string")" ||
                    return 1 ;;
        *) return 1 ;;
    esac

    compiler_probe_kinds[compiler_probe_count]="$kind"
    compiler_probe_commands[compiler_probe_count]="$command_string"
    compiler_probe_values[compiler_probe_count]="$result"
    compiler_probe_count=$((compiler_probe_count + 1))
    printf -v "$destination" '%s' "$result"
}

# Apple defaults must follow the active Xcode or standalone CLT root.
source "$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/whp-build/macos-developer-tools.sh"
APPLE_CLANG="$(whp_apple_find_tool clang)" || return 1 2>/dev/null || exit 1
APPLE_CLANGXX="$(whp_apple_find_tool clang++)" || return 1 2>/dev/null || exit 1

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

compiler_probe_once cc_family family CC "$CC" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once cxx_family family CXX "$CXX" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once objc_family family OBJC "$OBJC" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once build_cc_family family CC_FOR_BUILD "$CC_FOR_BUILD" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once build_cxx_family family CXX_FOR_BUILD "$CXX_FOR_BUILD" || \
    return 1 2>/dev/null || exit 1

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

compiler_probe_once MACOS_CC_TARGET_TRIPLE target CC "$CC" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once MACOS_CXX_TARGET_TRIPLE target CXX "$CXX" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once MACOS_OBJC_TARGET_TRIPLE target OBJC "$OBJC" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once MACOS_BUILD_CC_TARGET_TRIPLE target CC_FOR_BUILD "$CC_FOR_BUILD" || \
    return 1 2>/dev/null || exit 1
compiler_probe_once MACOS_BUILD_CXX_TARGET_TRIPLE target CXX_FOR_BUILD "$CXX_FOR_BUILD" || \
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
        if [[ "${QEMU_HOST_LTO_MODE:-auto}" != auto ]]; then
            printf '%s\n' \
                'error: explicit QEMU_HOST_LTO_MODE requires a supported Clang LTO toolchain on macOS.' >&2
            return 1 2>/dev/null || exit 1
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