#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_BUILD_BASH=${WHP_BUILD_BASH:-}
MACOS_ALLOW_MIXED_HOMEBREW=${MACOS_ALLOW_MIXED_HOMEBREW:-0}
POWERPC_BINUTILS_GIT_REF=${POWERPC_BINUTILS_GIT_REF:-binutils_2.46-branch}
export POWERPC_BINUTILS_GIT_REF

case "$MACOS_ALLOW_MIXED_HOMEBREW" in
    0|1) ;;
    *)
        printf 'error: MACOS_ALLOW_MIXED_HOMEBREW must be 0 or 1\n' >&2
        exit 1
        ;;
esac

if [ -z "$WHP_BUILD_BASH" ]; then
    if [ "$(uname -s 2>/dev/null || printf unknown)" = Darwin ] &&
       [ -x /bin/bash ]; then
        WHP_BUILD_BASH=/bin/bash
    else
        WHP_BUILD_BASH=$(command -v bash 2>/dev/null || true)
    fi
fi

if [ -z "$WHP_BUILD_BASH" ] || [ ! -x "$WHP_BUILD_BASH" ]; then
    printf '%s\n' \
        'error: GNU Bash is required for the macOS build wrapper.' \
        'Set WHP_BUILD_BASH to an executable Bash path.' >&2
    exit 1
fi

if ! "$WHP_BUILD_BASH" --noprofile --norc -c '
    test -n "${BASH_VERSION:-}" || exit 1
    test "${BASH_VERSINFO[0]}" -gt 3 ||
        { test "${BASH_VERSINFO[0]}" -eq 3 &&
          test "${BASH_VERSINFO[1]}" -ge 2; }
' >/dev/null 2>&1; then
    printf 'error: WHP_BUILD_BASH is not GNU Bash 3.2 or newer: %s\n' \
        "$WHP_BUILD_BASH" >&2
    exit 1
fi

if { [ -n "${OPENBIOS_HOSTCC:-}" ] && [ -z "${OPENBIOS_HOSTCXX:-}" ]; } ||
   { [ -z "${OPENBIOS_HOSTCC:-}" ] && [ -n "${OPENBIOS_HOSTCXX:-}" ]; }; then
    printf '%s\n' \
        'error: OPENBIOS_HOSTCC and OPENBIOS_HOSTCXX must be selected as a pair.' \
        "OPENBIOS_HOSTCC=${OPENBIOS_HOSTCC:-<unset>}" \
        "OPENBIOS_HOSTCXX=${OPENBIOS_HOSTCXX:-<unset>}" >&2
    exit 1
fi

# Keep QEMU and Cocoa on Apple Clang, but prefer a native GNU GCC pair for
# OpenBIOS host tools and the nested PowerPC binutils/GCC bootstrap.  Select
# GCC from the Homebrew prefix that matches the running process architecture;
# an Intel Homebrew installation must not leak into an arm64 build or vice
# versa.  Explicit OPENBIOS_HOSTCC/HOSTCXX settings always win.
if [ -z "${OPENBIOS_HOSTCC:-}" ] && [ -z "${OPENBIOS_HOSTCXX:-}" ]; then
    process_arch=$(uname -m 2>/dev/null || printf unknown)
    expected_brew=
    expected_machine=
    case "$process_arch" in
        arm64|aarch64)
            expected_brew=/opt/homebrew/bin/brew
            expected_machine=aarch64
            ;;
        x86_64|amd64)
            expected_brew=/usr/local/bin/brew
            expected_machine=x86_64
            ;;
    esac

    gcc_search_path=${PATH:-/usr/bin:/bin}
    brew_command=
    if [ -n "$expected_brew" ] && [ -x "$expected_brew" ]; then
        brew_command=$expected_brew
    elif [ "$MACOS_ALLOW_MIXED_HOMEBREW" = 1 ] &&
         command -v brew >/dev/null 2>&1; then
        brew_command=$(command -v brew)
    fi
    if [ -n "$brew_command" ]; then
        gcc_prefix=$($brew_command --prefix gcc 2>/dev/null || true)
        if [ -n "$gcc_prefix" ] && [ -d "$gcc_prefix/bin" ]; then
            gcc_search_path=$gcc_prefix/bin:$gcc_search_path
        fi
    fi

    for gcc_version in 16 15 14 13 12; do
        gcc_candidate=$(PATH=$gcc_search_path command -v gcc-$gcc_version 2>/dev/null || true)
        gxx_candidate=$(PATH=$gcc_search_path command -v g++-$gcc_version 2>/dev/null || true)
        [ -n "$gcc_candidate" ] && [ -n "$gxx_candidate" ] || continue

        compiler_macros=$($gcc_candidate -dM -E -x c /dev/null 2>/dev/null || true)
        printf '%s\n' "$compiler_macros" | grep -q '^#define __GNUC__ ' || continue
        if printf '%s\n' "$compiler_macros" | grep -q '^#define __clang__ '; then
            continue
        fi

        compiler_machine=$($gcc_candidate -dumpmachine 2>/dev/null || true)
        case "$expected_machine:$compiler_machine" in
            aarch64:aarch64-apple-darwin*|aarch64:arm64-apple-darwin*|\
            x86_64:x86_64-apple-darwin*) ;;
            *) continue ;;
        esac

        OPENBIOS_HOSTCC=$gcc_candidate
        OPENBIOS_HOSTCXX=$gxx_candidate
        export OPENBIOS_HOSTCC OPENBIOS_HOSTCXX
        printf '%s\n' \
            "PowerPC firmware host CC:  $OPENBIOS_HOSTCC" \
            "PowerPC firmware host CXX: $OPENBIOS_HOSTCXX"
        break
    done
fi

CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the build shell environment\n' >&2
    exit 1
fi
CONFIG_SHELL=${QEMU_CONFIG_SHELL:-$WHP_BUILD_BASH}
export WHP_BUILD_BASH CONFIG_SHELL MACOS_ALLOW_MIXED_HOMEBREW

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    "$WHP_BUILD_BASH" --noprofile --norc \
    "$SCRIPT_DIR/macos-builder.bash" "$@"
