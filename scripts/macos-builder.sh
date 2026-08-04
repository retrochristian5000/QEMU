#!/bin/sh

set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_BUILD_BASH=${WHP_BUILD_BASH:-}
MACOS_ALLOW_MIXED_HOMEBREW=${MACOS_ALLOW_MIXED_HOMEBREW:-0}
POWERPC_BINUTILS_GIT_REF=${POWERPC_BINUTILS_GIT_REF:-binutils_2.46-branch}
WHP_BUILD_ENTRY_NORMALIZED=1
export POWERPC_BINUTILS_GIT_REF WHP_BUILD_ENTRY_NORMALIZED

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

# The integrated macOS policy selects Apple Clang for build-machine tools,
# including OpenBIOS utilities and the PowerPC cross-toolchain bootstrap.
# A matching explicit OPENBIOS_HOSTCC/HOSTCXX pair remains available for
# controlled compiler experiments; do not change compiler family merely
# because a Homebrew GCC happens to be installed.

CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the build shell environment\n' >&2
    exit 1
fi
CONFIG_SHELL=${QEMU_CONFIG_SHELL:-$WHP_BUILD_BASH}
export WHP_BUILD_BASH CONFIG_SHELL MACOS_ALLOW_MIXED_HOMEBREW \
    WHP_BUILD_ENTRY_NORMALIZED

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    WHP_BUILD_ENTRY_NORMALIZED="$WHP_BUILD_ENTRY_NORMALIZED" \
    "$WHP_BUILD_BASH" --noprofile --norc \
    "$SCRIPT_DIR/macos-builder.bash" "$@"
