#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

# Normal local builds refresh the tracked QEMU branch before any tool or
# configuration discovery.  Probe/menu invocations stay side-effect free unless
# the caller explicitly sets WHP_SOURCE_UPDATE=1.
WHP_SOURCE_UPDATE=${WHP_SOURCE_UPDATE:-auto}
case "$WHP_SOURCE_UPDATE" in
    auto|0|1) ;;
    *)
        printf 'error: WHP_SOURCE_UPDATE must be auto, 0, or 1: %s\n' \
            "$WHP_SOURCE_UPDATE" >&2
        exit 1
        ;;
esac

WHP_SOURCE_UPDATE_SKIP=0
if [ "$WHP_SOURCE_UPDATE" = auto ]; then
    case "${1:-}" in
        menuconfig) WHP_SOURCE_UPDATE_SKIP=1 ;;
    esac
    if [ "${WHP_SHELL_PROBE_ONLY:-0}" = 1 ] ||
       [ "${WHP_BUILD_DIR_PROBE_ONLY:-0}" = 1 ] ||
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" = 1 ]; then
        WHP_SOURCE_UPDATE_SKIP=1
    fi
fi

if [ "${WHP_SOURCE_UPDATE_DONE:-0}" != 1 ] &&
   [ "$WHP_SOURCE_UPDATE" != 0 ] &&
   [ "$WHP_SOURCE_UPDATE_SKIP" != 1 ]; then
    WHP_SOURCE_REVISION_BEFORE=$(
        git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true
    )
    WHP_SOURCE_UPDATE="$WHP_SOURCE_UPDATE" \
        /bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"
    WHP_SOURCE_REVISION_AFTER=$(
        git -C "$SOURCE_DIR" rev-parse HEAD 2>/dev/null || true
    )

    WHP_SOURCE_UPDATE_DONE=1
    export WHP_SOURCE_UPDATE_DONE

    if [ -n "$WHP_SOURCE_REVISION_BEFORE" ] &&
       [ -n "$WHP_SOURCE_REVISION_AFTER" ] &&
       [ "$WHP_SOURCE_REVISION_BEFORE" != "$WHP_SOURCE_REVISION_AFTER" ]; then
        printf 'WHP source update: re-entering updated build.sh (%s -> %s)\n' \
            "$WHP_SOURCE_REVISION_BEFORE" "$WHP_SOURCE_REVISION_AFTER" >&2
        exec "$SOURCE_DIR/build.sh" "$@"
    fi
    unset WHP_SOURCE_REVISION_BEFORE WHP_SOURCE_REVISION_AFTER
fi
unset WHP_SOURCE_UPDATE_SKIP
export WHP_SOURCE_UPDATE

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
                        "$python_launcher" -c 'import sys; print(sys.executable)' \
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

# If the host has no usable interpreter, bootstrap the pinned WHP Python fork.
# Explicit PYTHON remains authoritative: only automatic discovery reaches this
# fallback.
if [ -z "${PYTHON:-}" ]; then
    PYTHON=$(/bin/sh "$SOURCE_DIR/scripts/bootstrap-python.sh") || exit 1
    if ! whp_python_usable "$PYTHON"; then
        printf 'error: bundled WHP Python is not Python 3.9 or newer: %s\n' \
            "${PYTHON:-<missing>}" >&2
        exit 1
    fi
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

# Saved configuration supplies portable policy defaults. Explicit environment
# variables remain one-run overrides and therefore take precedence. Load it
# before selecting Ninja so menuconfig can choose the build executor used by
# both the LLVM bootstrap and QEMU itself.
WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG") || exit 1
eval "$WHP_CONFIG_ENV"
unset WHP_CONFIG_ENV

BOOTSTRAP_NINJA=${BOOTSTRAP_NINJA:-auto}
case "$BOOTSTRAP_NINJA" in
    y) BOOTSTRAP_NINJA=1 ;;
    n) BOOTSTRAP_NINJA=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_NINJA must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_NINJA

# QEMU's normal Meson path needs Ninja before configuration, not only when the
# final build command is launched. An explicit NINJA_CMD is authoritative.
# On macOS, auto prefers the pinned WHP Ninja so the process-launch fast path
# is used even when Homebrew Ninja is installed; it falls back to a host Ninja
# if the optional bundled bootstrap is unavailable. Other hosts keep the
# host-first auto policy. 1 forces the pinned fork, and 0 requires a host Ninja.
# Export NINJA as well as NINJA_CMD so QEMU/Meson and WHP helpers consume one
# exact executable.
if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ]; then
    WHP_PREFER_BUNDLED_NINJA=0
    WHP_BUNDLED_NINJA_TRIED=0
    if [ "$BOOTSTRAP_NINJA" = auto ] && [ "$WHP_HOST_OS" = macos ]; then
        WHP_PREFER_BUNDLED_NINJA=1
    fi

    if [ -z "${NINJA_CMD:-}" ] && [ "$WHP_PREFER_BUNDLED_NINJA" = 1 ]; then
        WHP_BUNDLED_NINJA_TRIED=1
        NINJA_CMD=$("$PYTHON" "$SOURCE_DIR/scripts/ensure-ninja.py" \
            --build-dir "$BUILD_DIR") || NINJA_CMD=
    fi
    if [ -z "${NINJA_CMD:-}" ] && [ "$BOOTSTRAP_NINJA" != 1 ]; then
        NINJA_CMD=$(command -v ninja 2>/dev/null || command -v ninja-build 2>/dev/null || true)
    fi
    if [ -z "${NINJA_CMD:-}" ] && [ "$BOOTSTRAP_NINJA" != 0 ] && \
       [ "$WHP_BUNDLED_NINJA_TRIED" != 1 ]; then
        NINJA_CMD=$("$PYTHON" "$SOURCE_DIR/scripts/ensure-ninja.py" \
            --build-dir "$BUILD_DIR") || exit 1
    fi
    if [ -z "${NINJA_CMD:-}" ]; then
        if [ "$BOOTSTRAP_NINJA" = 0 ]; then
            printf '%s\n' \
                'error: Ninja is required, but BOOTSTRAP_NINJA=0 disables the bundled fallback.' \
                'Install Ninja or set NINJA_CMD.' >&2
        else
            printf '%s\n' \
                'error: no usable Ninja was found and the pinned WHP Ninja bootstrap failed.' \
                'Install Ninja, set NINJA_CMD, or check the bundled Ninja bootstrap diagnostics.' >&2
        fi
        exit 1
    fi
    unset WHP_PREFER_BUNDLED_NINJA WHP_BUNDLED_NINJA_TRIED
    case "$NINJA_CMD" in
        */*)
            NINJA_DIR=$(dirname -- "$NINJA_CMD")
            PATH="$NINJA_DIR:$PATH"
            unset NINJA_DIR
            ;;
    esac
    NINJA=$NINJA_CMD
    export NINJA_CMD NINJA PATH
fi

BOOTSTRAP_SDL=${BOOTSTRAP_SDL:-auto}
case "$BOOTSTRAP_SDL" in
    y) BOOTSTRAP_SDL=1 ;;
    n) BOOTSTRAP_SDL=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_SDL must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_SDL

# SDL3 is a normal QEMU host dependency, so keep QEMU's Meson dependency
# detection authoritative. The WHP bootstrap only provides a pinned private
# prefix and makes it visible through pkg-config/CMake. auto keeps a usable
# host SDL3, otherwise it falls back to the pinned SDL fork when the bootstrap
# prerequisites are available. 1 forces the fork; 0 disables only the bundled
# fallback and leaves normal host dependency discovery untouched.
if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "$BOOTSTRAP_SDL" != 0 ]; then
    SDL_BOOTSTRAP_MODE=auto
    if [ "$BOOTSTRAP_SDL" = 1 ]; then
        SDL_BOOTSTRAP_MODE=force
    fi
    WHP_SDL_PREFIX=$(
        "$PYTHON" "$SOURCE_DIR/scripts/ensure-sdl.py" \
            --build-dir "$BUILD_DIR" --mode "$SDL_BOOTSTRAP_MODE"
    ) || exit 1
    unset SDL_BOOTSTRAP_MODE

    if [ -n "$WHP_SDL_PREFIX" ]; then
        WHP_SDL_PC_PATH=
        for WHP_SDL_PC_DIR in \
            "$WHP_SDL_PREFIX/lib/pkgconfig" \
            "$WHP_SDL_PREFIX/lib64/pkgconfig" \
            "$WHP_SDL_PREFIX/libdata/pkgconfig"; do
            if [ -d "$WHP_SDL_PC_DIR" ]; then
                WHP_SDL_PC_PATH="${WHP_SDL_PC_PATH:+$WHP_SDL_PC_PATH:}$WHP_SDL_PC_DIR"
            fi
        done
        if [ -n "$WHP_SDL_PC_PATH" ]; then
            PKG_CONFIG_PATH="$WHP_SDL_PC_PATH${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
            export PKG_CONFIG_PATH
        fi
        CMAKE_PREFIX_PATH="$WHP_SDL_PREFIX${CMAKE_PREFIX_PATH:+:$CMAKE_PREFIX_PATH}"
        SDL3_ROOT="$WHP_SDL_PREFIX"
        export WHP_SDL_PREFIX CMAKE_PREFIX_PATH SDL3_ROOT
        unset WHP_SDL_PC_PATH WHP_SDL_PC_DIR
    fi
fi

BOOTSTRAP_LIBISOFS=${BOOTSTRAP_LIBISOFS:-auto}
case "$BOOTSTRAP_LIBISOFS" in
    y) BOOTSTRAP_LIBISOFS=1 ;;
    n) BOOTSTRAP_LIBISOFS=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_LIBISOFS must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_LIBISOFS

# libisofs is used only by the Darwin metadata-assisted ISO path. Keep Meson's
# dependency detection authoritative, but reject host headers which fail
# Clang's strict-prototype contract. auto uses a compatible host libisofs when
# available and otherwise stages the pinned WHP fork. 1 forces the fork.
if [ "$WHP_HOST_OS" = macos ] &&
   [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "$BOOTSTRAP_LIBISOFS" != 0 ]; then
    LIBISOFS_BOOTSTRAP_MODE=auto
    if [ "$BOOTSTRAP_LIBISOFS" = 1 ]; then
        LIBISOFS_BOOTSTRAP_MODE=force
    fi
    WHP_LIBISOFS_PREFIX=$(
        "$PYTHON" "$SOURCE_DIR/scripts/ensure-libisofs.py" \
            --build-dir "$BUILD_DIR" --mode "$LIBISOFS_BOOTSTRAP_MODE"
    ) || exit 1
    unset LIBISOFS_BOOTSTRAP_MODE

    if [ -n "$WHP_LIBISOFS_PREFIX" ]; then
        WHP_LIBISOFS_PC_PATH=
        for WHP_LIBISOFS_PC_DIR in \
            "$WHP_LIBISOFS_PREFIX/lib/pkgconfig" \
            "$WHP_LIBISOFS_PREFIX/lib64/pkgconfig" \
            "$WHP_LIBISOFS_PREFIX/libdata/pkgconfig"; do
            if [ -d "$WHP_LIBISOFS_PC_DIR" ]; then
                WHP_LIBISOFS_PC_PATH="${WHP_LIBISOFS_PC_PATH:+$WHP_LIBISOFS_PC_PATH:}$WHP_LIBISOFS_PC_DIR"
            fi
        done
        if [ -n "$WHP_LIBISOFS_PC_PATH" ]; then
            PKG_CONFIG_PATH="$WHP_LIBISOFS_PC_PATH${PKG_CONFIG_PATH:+:$PKG_CONFIG_PATH}"
            export PKG_CONFIG_PATH
        fi
        export WHP_LIBISOFS_PREFIX
        unset WHP_LIBISOFS_PC_PATH WHP_LIBISOFS_PC_DIR
    fi
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
    AR="$NATIVE_LLVM_DIR/bin/llvm-ar"
    RANLIB="$NATIVE_LLVM_DIR/bin/llvm-ranlib"
    NM="$NATIVE_LLVM_DIR/bin/llvm-nm"
    OBJC="$NATIVE_LLVM_DIR/bin/clang"
    PATH="$NATIVE_LLVM_DIR/bin:$PATH"
    WHP_SHARED_LLVM_DIR="$NATIVE_LLVM_DIR"
    export NATIVE_LLVM_DIR WHP_SHARED_LLVM_DIR CC CXX AR RANLIB NM OBJC PATH

    # Darwin host links must consume the same LLVM revision that produced the
    # LTO objects. Use the installed Mach-O LLD sibling through Clang's driver;
    # direct LD consumers get the same linker explicitly.
    if [ "$WHP_HOST_OS" = macos ]; then
        LD="$NATIVE_LLVM_DIR/bin/ld64.lld"
        NATIVE_LLVM_LDFLAG=-fuse-ld=lld
        case " ${LDFLAGS:-} " in
            *" $NATIVE_LLVM_LDFLAG "*) ;;
            *) LDFLAGS="${LDFLAGS:+$LDFLAGS }$NATIVE_LLVM_LDFLAG" ;;
        esac
        export LD NATIVE_LLVM_LDFLAG LDFLAGS
    fi
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
    "$SOURCE_DIR/builder.sh" "$@"
