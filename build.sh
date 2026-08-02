#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
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
        'error: GNU Bash is required for the WHP build wrapper.' \
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

# Non-interactive Bash can source BASH_ENV, and POSIX-like shells can use ENV.
# A build entry point must not inherit user startup code or POSIX mode.
CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the build shell environment\n' >&2
    exit 1
fi
CONFIG_SHELL=${QEMU_CONFIG_SHELL:-$WHP_BUILD_BASH}
export WHP_BUILD_BASH CONFIG_SHELL

if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ]; then
    exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
        -u SHELLOPTS -u BASHOPTS \
        WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
        "$WHP_BUILD_BASH" --noprofile --norc -c '
        printf "WHP build shell: %s\n" "$BASH_VERSION"
        printf "CONFIG_SHELL: %s\n" "$CONFIG_SHELL"
        case ":${SHELLOPTS:-}:" in
            *:posix:*) printf "error: Bash POSIX mode is active\n" >&2; exit 1 ;;
        esac
    '
fi

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
