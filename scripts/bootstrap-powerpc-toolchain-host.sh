#!/usr/bin/env bash

set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
CORE_BOOTSTRAP="$SCRIPT_DIR/bootstrap-powerpc-toolchain.sh"
POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST="${POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST:-0}"

case "$POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST" in
    0|1) ;;
    *)
        printf 'error: POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST must be 0 or 1\n' >&2
        exit 1
        ;;
esac

if [[ ! -x "$CORE_BOOTSTRAP" ]]; then
    printf 'error: PowerPC toolchain bootstrap is missing: %s\n' \
        "$CORE_BOOTSTRAP" >&2
    exit 1
fi

set_compiler_command()
{
    local command_string="$1"

    case "$command_string" in
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>')
            return 1
            ;;
    esac

    COMPILER_COMMAND=()
    read -r -a COMPILER_COMMAND <<< "$command_string"
    [[ "${#COMPILER_COMMAND[@]}" -gt 0 ]] || return 1
    command -v "${COMPILER_COMMAND[0]}" >/dev/null 2>&1
}

compiler_family()
{
    local command_string="$1"
    local macros

    set_compiler_command "$command_string" || {
        printf 'missing\n'
        return 0
    }
    macros="$("${COMPILER_COMMAND[@]}" -dM -E -x c /dev/null 2>/dev/null || true)"
    if grep -q '^#define __clang__ ' <<< "$macros"; then
        printf 'clang\n'
    elif grep -q '^#define __GNUC__ ' <<< "$macros"; then
        printf 'gcc\n'
    else
        printf 'unknown\n'
    fi
}

flags_contain_lto_or_plugin()
{
    local value="$1"
    local token
    local tokens=()

    read -r -a tokens <<< "$value"
    for token in "${tokens[@]}"; do
        case "$token" in
            -flto|-flto=*|-fno-lto|\
            -Wl,*lto*|-Wl,*LTO*|-Wl,*plugin*|\
            -fuse-ld=*|-object_path_lto*|-lto_library*|\
            -Xlinker=*lto*|-Xlinker=*LTO*|-Xlinker=*plugin*)
                return 0
                ;;
        esac
    done
    return 1
}

for flag_variable in \
    TOOLCHAIN_HOST_CFLAGS TOOLCHAIN_HOST_CXXFLAGS \
    TOOLCHAIN_HOST_CPPFLAGS TOOLCHAIN_HOST_LDFLAGS; do
    flag_value="${!flag_variable:-}"
    if [[ -n "$flag_value" ]] && flags_contain_lto_or_plugin "$flag_value"; then
        printf '%s\n' \
            "error: $flag_variable contains an LTO or linker-plugin option:" \
            "  $flag_value" \
            'The PowerPC bootstrap builds binutils before GCC and must not' \
            'inherit QEMU host LTO or a compiler-specific linker plugin.' >&2
        exit 1
    fi
done

selected_cc="${POWERPC_TOOLCHAIN_HOST_CC:-${TOOLCHAIN_HOST_CC:-}}"
selected_cxx="${POWERPC_TOOLCHAIN_HOST_CXX:-${TOOLCHAIN_HOST_CXX:-}}"

if [[ -n "$selected_cc" || -n "$selected_cxx" ]]; then
    if [[ -z "$selected_cc" || -z "$selected_cxx" ]]; then
        printf '%s\n' \
            'error: the PowerPC toolchain host C and C++ compilers must be set as a pair.' \
            "C compiler:   ${selected_cc:-<unset>}" \
            "C++ compiler: ${selected_cxx:-<unset>}" >&2
        exit 1
    fi
elif [[ "$(uname -s)" == "Darwin" ]]; then
    for gcc_version in 16 15 14 13 12; do
        gcc_candidate="gcc-$gcc_version"
        gxx_candidate="g++-$gcc_version"
        if command -v "$gcc_candidate" >/dev/null 2>&1 &&
           command -v "$gxx_candidate" >/dev/null 2>&1 &&
           [[ "$(compiler_family "$gcc_candidate")" == gcc ]] &&
           [[ "$(compiler_family "$gxx_candidate")" == gcc ]]; then
            selected_cc="$(command -v "$gcc_candidate")"
            selected_cxx="$(command -v "$gxx_candidate")"
            break
        fi
    done

    if [[ -z "$selected_cc" ]]; then
        if [[ "$POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST" == "1" ]]; then
            printf '%s\n' \
                'error: no versioned GNU GCC host compiler was found on macOS.' \
                'Install a native GNU GCC pair or set POWERPC_TOOLCHAIN_HOST_CC' \
                'and POWERPC_TOOLCHAIN_HOST_CXX explicitly.' >&2
            exit 1
        fi
        selected_cc="$(xcrun --sdk macosx --find clang)"
        selected_cxx="$(xcrun --sdk macosx --find clang++)"
        printf '%s\n' \
            'warning: GNU GCC was not found for the PowerPC toolchain bootstrap.' \
            'Falling back to Apple Clang with LTO and linker-plugin flags isolated.' >&2
    fi
else
    selected_cc="${CC_FOR_BUILD:-${CC:-cc}}"
    selected_cxx="${CXX_FOR_BUILD:-${CXX:-c++}}"
fi

cc_family="$(compiler_family "$selected_cc")"
cxx_family="$(compiler_family "$selected_cxx")"
if [[ "$cc_family" == missing || "$cxx_family" == missing ||
      "$cc_family" == unknown || "$cxx_family" == unknown ]]; then
    printf '%s\n' \
        'error: could not identify the selected PowerPC toolchain host compilers.' \
        "CC=$selected_cc ($cc_family)" \
        "CXX=$selected_cxx ($cxx_family)" >&2
    exit 1
fi
if [[ "$cc_family" != "$cxx_family" ]]; then
    printf '%s\n' \
        'error: mixed compiler families are not allowed in the PowerPC bootstrap.' \
        "CC=$selected_cc ($cc_family)" \
        "CXX=$selected_cxx ($cxx_family)" >&2
    exit 1
fi
if [[ "$(uname -s)" == "Darwin" &&
      "$POWERPC_TOOLCHAIN_REQUIRE_GNU_HOST" == "1" &&
      "$cc_family" != gcc ]]; then
    printf 'error: GNU GCC is required but %s identifies as %s\n' \
        "$selected_cc" "$cc_family" >&2
    exit 1
fi

export TOOLCHAIN_HOST_CC="$selected_cc"
export TOOLCHAIN_HOST_CXX="$selected_cxx"

printf '%s\n' \
    "PowerPC toolchain host CC:  $TOOLCHAIN_HOST_CC ($cc_family)" \
    "PowerPC toolchain host CXX: $TOOLCHAIN_HOST_CXX ($cxx_family)"

exec bash "$CORE_BOOTSTRAP" "$@"
