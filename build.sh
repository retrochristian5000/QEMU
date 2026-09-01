#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
WHP_CONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/config.py"
WHP_MENUCONFIG_TOOL="$SOURCE_DIR/scripts/whp-config/menuconfig.py"
WHP_PORTABLE_BUILD_TOOL="$SOURCE_DIR/scripts/whp-build/portable-build-entry.py"
WHP_USER_CONFIG="$SOURCE_DIR/.whpconfig"

if [ -n "${WHP_BUILD_BASH:-}" ]; then
    WHP_BUILD_BASH_EXPLICIT=1
else
    WHP_BUILD_BASH_EXPLICIT=0
    WHP_BUILD_BASH=
fi

WHP_BUILD_SHELL=${WHP_BUILD_SHELL:-auto}
case "$WHP_BUILD_SHELL" in
    auto|bash|zsh) ;;
    portable)
        WHP_FORCE_PORTABLE_CORE=1
        ;;
    *)
        printf 'error: WHP_BUILD_SHELL must be auto, bash, zsh, or portable: %s\n' \
            "$WHP_BUILD_SHELL" >&2
        exit 1
        ;;
esac

whp_python_usable()
{
    [ -n "${1:-}" ] || return 1
    "$1" -c 'import sys; raise SystemExit(sys.version_info < (3, 9))' \
        >/dev/null 2>&1
}

if [ -n "${PYTHON:-}" ]; then
    if ! whp_python_usable "$PYTHON"; then
        printf 'error: PYTHON is not Python 3.9 or newer: %s\n' "$PYTHON" >&2
        exit 1
    fi
else
    PYTHON=
    for python_name in python3 python; do
        python_candidate=$(command -v "$python_name" 2>/dev/null || true)
        if whp_python_usable "$python_candidate"; then
            PYTHON=$python_candidate
            break
        fi
    done

    # Windows installations may expose only the Python launcher even when a
    # runtime is installed, and Store aliases named python/python3 may exist
    # without being usable from the current MSYS shell. Resolve the launcher to
    # the real interpreter so downstream configure/Meson calls receive an
    # executable path rather than launcher-specific semantics.
    if [ -z "$PYTHON" ]; then
        case "$(uname -s 2>/dev/null || true)" in
            CYGWIN*|MINGW*|MSYS*)
                python_launcher=$(command -v py 2>/dev/null || true)
                if [ -n "$python_launcher" ]; then
                    python_candidate=$(
                        "$python_launcher" -c \
                            'import sys; print(sys.executable) if sys.version_info >= (3, 9) else raise SystemExit(1)' \
                            2>/dev/null || true
                    )
                    if whp_python_usable "$python_candidate"; then
                        PYTHON=$python_candidate
                    fi
                fi
                unset python_launcher
                ;;
        esac
    fi
    unset python_name python_candidate
fi

if [ -z "${PYTHON:-}" ]; then
    printf 'error: Python 3.9 or newer is required by QEMU and the WHP build configuration\n' >&2
    exit 1
fi
export PYTHON WHP_USER_CONFIG

# Detect the host once at the public build boundary. Helpers consume this
# normalized identity instead of independently interpreting uname output, which
# differs across Darwin, Linux, MSYS2/MinGW/Cygwin, BSD, and other hosts.
WHP_HOST_KERNEL=$(uname -s 2>/dev/null || printf unknown)
WHP_HOST_ARCH=$(uname -m 2>/dev/null || printf unknown)
case "$WHP_HOST_KERNEL" in
    Darwin)
        WHP_HOST_OS=macos
        WHP_HOST_NAME=macOS
        ;;
    Linux)
        WHP_HOST_OS=linux
        WHP_HOST_NAME=Linux
        ;;
    CYGWIN*|MINGW*|MSYS*)
        WHP_HOST_OS=windows
        WHP_HOST_NAME=Windows
        ;;
    FreeBSD)
        WHP_HOST_OS=freebsd
        WHP_HOST_NAME=FreeBSD
        ;;
    NetBSD)
        WHP_HOST_OS=netbsd
        WHP_HOST_NAME=NetBSD
        ;;
    OpenBSD)
        WHP_HOST_OS=openbsd
        WHP_HOST_NAME=OpenBSD
        ;;
    DragonFly)
        WHP_HOST_OS=dragonfly
        WHP_HOST_NAME=DragonFlyBSD
        ;;
    SunOS)
        WHP_HOST_OS=solaris
        WHP_HOST_NAME=Solaris
        ;;
    Haiku)
        WHP_HOST_OS=haiku
        WHP_HOST_NAME=Haiku
        ;;
    *)
        WHP_HOST_OS=other
        WHP_HOST_NAME="$WHP_HOST_KERNEL"
        ;;
esac
export WHP_HOST_OS WHP_HOST_KERNEL WHP_HOST_ARCH
printf 'WHP host: %s (%s/%s)\n' \
    "$WHP_HOST_NAME" "$WHP_HOST_KERNEL" "$WHP_HOST_ARCH" >&2
unset WHP_HOST_NAME

# Resolve BUILD_DIR exactly once before choosing the Bash or portable runner.
# This prevents shell availability from selecting a different QEMU build tree,
# makes relative overrides source-relative, and gives read-only source trees a
# writable cache fallback when possible.
BUILD_DIR=$("$PYTHON" "$WHP_PORTABLE_BUILD_TOOL" --print-build-dir) || exit 1
export BUILD_DIR

if [ "${WHP_BUILD_DIR_PROBE_ONLY:-0}" = 1 ]; then
    printf 'BUILD_DIR=%s\n' "$BUILD_DIR"
    exit 0
fi

if [ "${1:-}" = menuconfig ]; then
    shift
    exec "$PYTHON" "$WHP_MENUCONFIG_TOOL" "$WHP_USER_CONFIG" "$@"
fi

# QEMU's normal Meson path needs Ninja before configuration, not only when the
# final build command is launched. Prefer an explicitly selected or system
# Ninja, but lazily bootstrap the pinned WHP Ninja fork when the host does not
# provide one. The fallback lives beside BUILD_DIR so the QEMU build tree stays
# empty until its ownership marker is established.
if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ]; then
    if [ -z "${NINJA_CMD:-}" ]; then
        NINJA_CMD=$(command -v ninja 2>/dev/null || command -v ninja-build 2>/dev/null || true)
    fi
    if [ -z "${NINJA_CMD:-}" ]; then
        NINJA_CMD=$("$PYTHON" "$SOURCE_DIR/scripts/ensure-ninja.py" --build-dir "$BUILD_DIR") || exit 1
        NINJA_DIR=$(dirname -- "$NINJA_CMD")
        PATH="$NINJA_DIR:$PATH"
        export PATH
        unset NINJA_DIR
    fi
    export NINJA_CMD PATH
fi

if [ -z "$WHP_BUILD_BASH" ]; then
    if [ "$WHP_HOST_OS" = macos ] && [ -x /bin/bash ]; then
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

# zsh is the default interactive shell on current macOS releases, but the WHP
# implementation graph intentionally remains Bash. Let zsh own the macOS
# orchestration boundary while keeping Bash as CONFIG_SHELL and as the explicit
# interpreter for Bash-only helpers. -f prevents user zsh startup files from
# changing build semantics.
WHP_BUILD_FRONTEND_KIND=bash
WHP_BUILD_FRONTEND_SHELL="$WHP_BUILD_BASH"
if [ "$WHP_HOST_OS" = macos ]; then
    case "$WHP_BUILD_SHELL" in
        auto|zsh)
            if [ -x /bin/zsh ]; then
                WHP_ZSH=/bin/zsh
            else
                WHP_ZSH=$(command -v zsh 2>/dev/null || true)
            fi
            if [ -n "$WHP_ZSH" ] &&
               "$WHP_ZSH" -f -c 'test -n "${ZSH_VERSION:-}"' >/dev/null 2>&1; then
                WHP_BUILD_FRONTEND_KIND=zsh
                WHP_BUILD_FRONTEND_SHELL="$WHP_ZSH"
            elif [ "$WHP_BUILD_SHELL" = zsh ]; then
                printf 'error: WHP_BUILD_SHELL=zsh requires a usable zsh\n' >&2
                exit 1
            fi
            unset WHP_ZSH
            ;;
        bash) ;;
    esac
elif [ "$WHP_BUILD_SHELL" = zsh ]; then
    printf 'error: WHP_BUILD_SHELL=zsh is currently supported only on macOS\n' >&2
    exit 1
fi
export WHP_BUILD_SHELL WHP_BUILD_FRONTEND_KIND WHP_BUILD_FRONTEND_SHELL

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
    NATIVE_LLVM_FORCE_REBUILD=${NATIVE_LLVM_FORCE_REBUILD:-0}
else
    OPENBIOS_FORCE_RECONFIGURE=${OPENBIOS_FORCE_RECONFIGURE:-1}
    POWERPC_TOOLCHAIN_FORCE_REBUILD=${POWERPC_TOOLCHAIN_FORCE_REBUILD:-1}
    NATIVE_LLVM_FORCE_REBUILD=${NATIVE_LLVM_FORCE_REBUILD:-1}
fi
export WHP_INCREMENTAL_BUILD OPENBIOS_FORCE_RECONFIGURE \
    POWERPC_TOOLCHAIN_FORCE_REBUILD NATIVE_LLVM_FORCE_REBUILD

BOOTSTRAP_NATIVE_LLVM=${BOOTSTRAP_NATIVE_LLVM:-0}
case "$BOOTSTRAP_NATIVE_LLVM" in
    0|1) ;;
    *)
        printf 'error: BOOTSTRAP_NATIVE_LLVM must be 0 or 1\n' >&2
        exit 1
        ;;
esac
if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then
    NATIVE_LLVM_DIR=$("$WHP_BUILD_BASH" --noprofile --norc \
        "$SOURCE_DIR/scripts/bootstrap-native-clang.sh") || exit 1
    CC="$NATIVE_LLVM_DIR/bin/clang"
    CXX="$NATIVE_LLVM_DIR/bin/clang++"
    export NATIVE_LLVM_DIR CC CXX
    printf 'QEMU native compiler: WHP LLVM (%s)\n' "$NATIVE_LLVM_DIR"
fi

# One public shell choice owns every Bash-based helper. The core build path
# above does not need this setting at all.
unset QEMU_CONFIG_SHELL TOOLCHAIN_CONFIG_SHELL
CONFIG_SHELL="$WHP_BUILD_BASH"
WHP_BUILD_ENTRY_NORMALIZED=1
export WHP_BUILD_BASH CONFIG_SHELL WHP_BUILD_ENTRY_NORMALIZED

if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ]; then
    printf 'WHP orchestration shell: %s\n' "$WHP_BUILD_FRONTEND_KIND"
    exec "$WHP_BUILD_BASH" --noprofile --norc -c '
        printf "WHP build shell: %s\n" "$BASH_VERSION"
        printf "CONFIG_SHELL: %s\n" "$CONFIG_SHELL"
        case ":${SHELLOPTS:-}:" in
            *:posix:*) printf "error: Bash POSIX mode is active\n" >&2; exit 1 ;;
        esac
    '
fi

# macOS keeps its stricter SDK/compiler adapter when Bash is available. The
# portable core remains available with WHP_BUILD_SHELL=portable,
# WHP_FORCE_PORTABLE_CORE=1, or no usable Bash backend.
if [ "$WHP_HOST_OS" = macos ] &&
   [ "${WHP_SKIP_MACOS_WRAPPER:-0}" != 1 ]; then
    case "$WHP_BUILD_FRONTEND_KIND" in
        zsh)
            exec "$WHP_BUILD_FRONTEND_SHELL" -f \
                "$SOURCE_DIR/scripts/macos-builder.sh" "$@"
            ;;
        bash)
            exec "$WHP_BUILD_BASH" --noprofile --norc \
                "$SOURCE_DIR/scripts/macos-builder.sh" "$@"
            ;;
    esac
fi

# Non-interactive Bash can source BASH_ENV. Remove user startup hooks before
# handing the rest of the build to the normalized helper graph.
unset BASH_ENV ENV

exec "$WHP_BUILD_BASH" --noprofile --norc \
    "$SOURCE_DIR/scripts/whp-build/build-entry.bash" "$@"
