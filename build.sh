#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_CONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/config.py"
WHP_MENUCONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/menuconfig.py"
WHP_PORTABLE_BUILD_TOOL="$SOURCE_DIR/scripts/whp-build/portable-build.py"
WHP_USER_CONFIG="$SOURCE_DIR/.whpconfig"

if [ -n "${WHP_BUILD_BASH:-}" ]; then
    WHP_BUILD_BASH_EXPLICIT=1
else
    WHP_BUILD_BASH_EXPLICIT=0
    WHP_BUILD_BASH=
fi

if [ -z "${PYTHON:-}" ]; then
    PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
fi
if [ -z "${PYTHON:-}" ] ||
   ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' >/dev/null 2>&1; then
    printf 'error: Python 3.9 or newer is required by QEMU and the WHP build configuration\n' >&2
    exit 1
fi
export PYTHON WHP_USER_CONFIG

if [ "${1:-}" = menuconfig ]; then
    shift
    exec "$PYTHON" "$WHP_MENUCONFIG_TOOL" "$WHP_USER_CONFIG" "$@"
fi

if [ -z "$WHP_BUILD_BASH" ]; then
    if [ "$(uname -s 2>/dev/null || printf unknown)" = Darwin ] &&
       [ -x /bin/bash ]; then
        WHP_BUILD_BASH=/bin/bash
    else
        WHP_BUILD_BASH=$(command -v bash 2>/dev/null || true)
    fi
fi

portable_core()
{
    if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ]; then
        printf 'WHP build shell: unavailable (portable Python core)\n'
        printf 'CONFIG_SHELL: <QEMU configure default>\n'
        exit 0
    fi
    exec "$PYTHON" "$WHP_PORTABLE_BUILD_TOOL" "$@"
}

# The portable core is a real build path, not an error fallback. It keeps
# QEMU buildable on hosts that satisfy QEMU's prerequisites but do not provide
# a usable GNU Bash. CI can force this path even when Bash is installed.
if [ "${WHP_FORCE_PORTABLE_CORE:-0}" = 1 ] || [ -z "$WHP_BUILD_BASH" ]; then
    portable_core "$@"
fi

if [ ! -x "$WHP_BUILD_BASH" ]; then
    if [ "$WHP_BUILD_BASH_EXPLICIT" = 1 ]; then
        printf 'error: WHP_BUILD_BASH is not executable: %s\n' "$WHP_BUILD_BASH" >&2
        exit 1
    fi
    portable_core "$@"
fi

if ! "$WHP_BUILD_BASH" --noprofile --norc -c '
    test -n "${BASH_VERSION:-}" || exit 1
    test "${BASH_VERSINFO[0]}" -gt 3 ||
        { test "${BASH_VERSINFO[0]}" -eq 3 &&
          test "${BASH_VERSINFO[1]}" -ge 2; }
' >/dev/null 2>&1; then
    if [ "$WHP_BUILD_BASH_EXPLICIT" = 1 ]; then
        printf 'error: WHP_BUILD_BASH is not GNU Bash 3.2 or newer: %s\n' \
            "$WHP_BUILD_BASH" >&2
        exit 1
    fi
    portable_core "$@"
fi

# Saved configuration supplies portable policy defaults. Explicit environment
# variables remain one-run overrides and therefore take precedence.
WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG") || exit 1
eval "$WHP_CONFIG_ENV"
unset WHP_CONFIG_ENV

WHP_INCREMENTAL_BUILD=${WHP_INCREMENTAL_BUILD:-1}
case "$WHP_INCREMENTAL_BUILD" in
    0|1) ;;
    *)
        printf 'error: WHP_INCREMENTAL_BUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac

if [ "$WHP_INCREMENTAL_BUILD" = 1 ]; then
    OPENBIOS_FORCE_RECONFIGURE=${OPENBIOS_FORCE_RECONFIGURE:-0}
    POWERPC_TOOLCHAIN_FORCE_REBUILD=${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}
else
    OPENBIOS_FORCE_RECONFIGURE=${OPENBIOS_FORCE_RECONFIGURE:-1}
    POWERPC_TOOLCHAIN_FORCE_REBUILD=${POWERPC_TOOLCHAIN_FORCE_REBUILD:-1}
fi
export WHP_INCREMENTAL_BUILD OPENBIOS_FORCE_RECONFIGURE \
    POWERPC_TOOLCHAIN_FORCE_REBUILD

# One public shell choice owns every Bash-based helper. The core build path
# above does not need this setting at all.
unset QEMU_CONFIG_SHELL TOOLCHAIN_CONFIG_SHELL
CONFIG_SHELL="$WHP_BUILD_BASH"
WHP_BUILD_ENTRY_NORMALIZED=1
export WHP_BUILD_BASH CONFIG_SHELL WHP_BUILD_ENTRY_NORMALIZED

if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ]; then
    exec "$WHP_BUILD_BASH" --noprofile --norc -c '
        printf "WHP build shell: %s\n" "$BASH_VERSION"
        printf "CONFIG_SHELL: %s\n" "$CONFIG_SHELL"
        case ":${SHELLOPTS:-}:" in
            *:posix:*) printf "error: Bash POSIX mode is active\n" >&2; exit 1 ;;
        esac
    '
fi

# macOS keeps its stricter SDK/compiler adapter when Bash is available. The
# portable core remains available with WHP_FORCE_PORTABLE_CORE=1 or no Bash.
if [ "$(uname -s 2>/dev/null || printf unknown)" = Darwin ] &&
   [ "${WHP_SKIP_MACOS_WRAPPER:-0}" != 1 ]; then
    exec /bin/sh "$SOURCE_DIR/scripts/macos-builder.sh" "$@"
fi

# Non-interactive Bash can source BASH_ENV. Remove user startup hooks before
# entering the feature-rich Bash runner without depending on GNU env options.
unset BASH_ENV ENV POSIXLY_CORRECT 2>/dev/null || true
exec "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
