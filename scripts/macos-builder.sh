#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_BUILD_BASH=${WHP_BUILD_BASH:-}

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

# Keep QEMU and Cocoa on Apple Clang, but prefer a real GNU GCC pair for
# OpenBIOS host tools and the nested PowerPC binutils/GCC bootstrap.  Apple's
# unversioned gcc command is normally Clang, so only versioned GNU drivers are
# considered here.  Explicit OPENBIOS_HOSTCC/HOSTCXX settings always win.
if [ -z "${OPENBIOS_HOSTCC:-}" ] && [ -z "${OPENBIOS_HOSTCXX:-}" ]; then
    gcc_search_path=${PATH:-/usr/bin:/bin}
    if command -v brew >/dev/null 2>&1; then
        gcc_prefix=$(brew --prefix gcc 2>/dev/null || true)
        if [ -n "$gcc_prefix" ] && [ -d "$gcc_prefix/bin" ]; then
            gcc_search_path=$gcc_prefix/bin:$gcc_search_path
        fi
    fi

    for gcc_version in 16 15 14 13 12; do
        gcc_candidate=$(PATH=$gcc_search_path command -v gcc-$gcc_version 2>/dev/null || true)
        gxx_candidate=$(PATH=$gcc_search_path command -v g++-$gcc_version 2>/dev/null || true)
        if [ -n "$gcc_candidate" ] && [ -n "$gxx_candidate" ] &&
           "$gcc_candidate" -dM -E -x c /dev/null 2>/dev/null |
               grep -q '^#define __GNUC__ ' &&
           ! "$gcc_candidate" -dM -E -x c /dev/null 2>/dev/null |
               grep -q '^#define __clang__ '; then
            OPENBIOS_HOSTCC=$gcc_candidate
            OPENBIOS_HOSTCXX=$gxx_candidate
            export OPENBIOS_HOSTCC OPENBIOS_HOSTCXX
            printf '%s\n' \
                "PowerPC firmware host CC:  $OPENBIOS_HOSTCC" \
                "PowerPC firmware host CXX: $OPENBIOS_HOSTCXX"
            break
        fi
    done
fi

CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the build shell environment\n' >&2
    exit 1
fi
CONFIG_SHELL=${QEMU_CONFIG_SHELL:-$WHP_BUILD_BASH}
export WHP_BUILD_BASH CONFIG_SHELL

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    "$WHP_BUILD_BASH" --noprofile --norc \
    "$SCRIPT_DIR/macos-builder.bash" "$@"
