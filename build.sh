#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_CONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/config.py"
WHP_MENUCONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/menuconfig.py"
WHP_USER_CONFIG="$SOURCE_DIR/.whpconfig"
WHP_BUILD_BASH=${WHP_BUILD_BASH:-}

if [ -z "${PYTHON:-}" ]; then
    PYTHON=$(command -v python3 2>/dev/null || command -v python 2>/dev/null || true)
fi
if [ -z "${PYTHON:-}" ] ||
   ! "$PYTHON" -c 'import sys; raise SystemExit(sys.version_info < (3, 8))' >/dev/null 2>&1; then
    printf 'error: Python 3.8 or newer is required for the WHP build configuration\n' >&2
    exit 1
fi
export PYTHON WHP_USER_CONFIG

if [ "${1:-}" = menuconfig ]; then
    shift
    exec "$PYTHON" "$WHP_MENUCONFIG_TOOL" "$WHP_USER_CONFIG" "$@"
fi

# Saved configuration supplies portable policy defaults. Explicit environment
# variables remain one-run overrides and therefore take precedence.
if [ -f "$WHP_USER_CONFIG" ]; then
    WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG") || exit 1
    eval "$WHP_CONFIG_ENV"
    unset WHP_CONFIG_ENV
fi

# QEMU's native Kconfig accepts per-target preset files through
# --with-devices-ARCH=NAME. Generate the PPC preset from the portable user
# configuration while retaining the repository's tracked defaults.
WHP_TARGET_LIST_FOR_CONFIG=${QEMU_TARGET_LIST:-ppc-softmmu}
case ",$WHP_TARGET_LIST_FOR_CONFIG," in
    *,ppc-softmmu,*)
        "$PYTHON" "$WHP_CONFIG_TOOL" --write-ppc-devices \
            "$WHP_USER_CONFIG" \
            "$SOURCE_DIR/configs/devices/ppc-softmmu/default.mak" \
            "$SOURCE_DIR/configs/devices/ppc-softmmu/whp-user.mak" || exit 1
        ;;
esac
unset WHP_TARGET_LIST_FOR_CONFIG

WHP_INCREMENTAL_BUILD=${WHP_INCREMENTAL_BUILD:-1}

case "$WHP_INCREMENTAL_BUILD" in
    0|1) ;;
    *)
        printf 'error: WHP_INCREMENTAL_BUILD must be 0 or 1\n' >&2
        exit 1
        ;;
esac

# Incremental rebuilds are the public default.  The QEMU Ninja tree already
# tracks source dependencies; keep firmware and cross-toolchain caches aligned
# with that policy unless the caller explicitly requests a forced rebuild.
if [ "$WHP_INCREMENTAL_BUILD" = 1 ]; then
    OPENBIOS_FORCE_RECONFIGURE=${OPENBIOS_FORCE_RECONFIGURE:-0}
    POWERPC_TOOLCHAIN_FORCE_REBUILD=${POWERPC_TOOLCHAIN_FORCE_REBUILD:-0}
else
    OPENBIOS_FORCE_RECONFIGURE=${OPENBIOS_FORCE_RECONFIGURE:-1}
    POWERPC_TOOLCHAIN_FORCE_REBUILD=${POWERPC_TOOLCHAIN_FORCE_REBUILD:-1}
fi
export WHP_INCREMENTAL_BUILD OPENBIOS_FORCE_RECONFIGURE \
    POWERPC_TOOLCHAIN_FORCE_REBUILD

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

# One public shell choice owns every configure recursion.  Older WHP aliases
# are deliberately discarded instead of carrying multiple names for the same
# decision.
unset QEMU_CONFIG_SHELL TOOLCHAIN_CONFIG_SHELL
CONFIG_SHELL="$WHP_BUILD_BASH"

# Non-interactive Bash can source BASH_ENV, and POSIX-like shells can use ENV.
# A build entry point must not inherit user startup code or POSIX mode.
CLEAN_ENV=$(command -v env 2>/dev/null || true)
if [ -z "$CLEAN_ENV" ]; then
    printf 'error: env is required to normalize the build shell environment\n' >&2
    exit 1
fi
WHP_BUILD_ENTRY_NORMALIZED=1
export WHP_BUILD_BASH CONFIG_SHELL WHP_BUILD_ENTRY_NORMALIZED

if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ]; then
    exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
        -u SHELLOPTS -u BASHOPTS \
        WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
        WHP_BUILD_ENTRY_NORMALIZED="$WHP_BUILD_ENTRY_NORMALIZED" \
        "$WHP_BUILD_BASH" --noprofile --norc -c '
        printf "WHP build shell: %s\n" "$BASH_VERSION"
        printf "CONFIG_SHELL: %s\n" "$CONFIG_SHELL"
        case ":${SHELLOPTS:-}:" in
            *:posix:*) printf "error: Bash POSIX mode is active\n" >&2; exit 1 ;;
        esac
    '
fi

# macOS needs SDK, architecture, Objective-C, compiler-family, and LTO policy
# before builder.sh computes its defaults.  Keep one public macOS path even
# when the user starts from the generic launcher.
if [ "$(uname -s 2>/dev/null || printf unknown)" = Darwin ] &&
   [ "${WHP_SKIP_MACOS_WRAPPER:-0}" != 1 ]; then
    exec /bin/sh "$SOURCE_DIR/scripts/macos-builder.sh" "$@"
fi

exec "$CLEAN_ENV" -u BASH_ENV -u ENV -u POSIXLY_CORRECT \
    -u SHELLOPTS -u BASHOPTS \
    WHP_BUILD_BASH="$WHP_BUILD_BASH" CONFIG_SHELL="$CONFIG_SHELL" \
    WHP_BUILD_ENTRY_NORMALIZED="$WHP_BUILD_ENTRY_NORMALIZED" \
    "$WHP_BUILD_BASH" --noprofile --norc "$SOURCE_DIR/builder.sh" "$@"
