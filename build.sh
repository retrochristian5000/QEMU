#!/bin/sh

set -eu

SOURCE_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

. "$SOURCE_DIR/scripts/whp-build/shell-functions.sh"

# Normal local builds refresh the tracked QEMU branch before any tool or
# configuration discovery.  Probe/menu invocations stay side-effect free unless
# the caller explicitly sets WHP_SOURCE_UPDATE=1.
WHP_SOURCE_UPDATE=$(whp_require_auto_switch WHP_SOURCE_UPDATE "${WHP_SOURCE_UPDATE:-auto}") || exit 1

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
WHP_MENUCONFIG_SHELL="$SOURCE_DIR/scripts/whp-config/menuconfig.sh"
WHP_PORTABLE_BUILD_TOOL="$SOURCE_DIR/scripts/whp-build/portable-build-entry.py"
WHP_USER_CONFIG="$SOURCE_DIR/.whpconfig"

whp_config_bootstrap_python()
{
    [ -f "$WHP_USER_CONFIG" ] || return 1
    whp_bootstrap_python_value=
    while IFS= read -r whp_config_line || [ -n "$whp_config_line" ]; do
        case "$whp_config_line" in
            BOOTSTRAP_PYTHON=*)
                whp_bootstrap_python_value=${whp_config_line#BOOTSTRAP_PYTHON=}
                ;;
        esac
    done < "$WHP_USER_CONFIG"
    [ -n "$whp_bootstrap_python_value" ] || return 1
    printf '%s\n' "$whp_bootstrap_python_value"
}

if [ -z "${BOOTSTRAP_PYTHON:-}" ]; then
    BOOTSTRAP_PYTHON=$(whp_config_bootstrap_python 2>/dev/null || printf 'auto\n')
fi
BOOTSTRAP_PYTHON=$(whp_normalize_auto_switch BOOTSTRAP_PYTHON "$BOOTSTRAP_PYTHON") || exit 1
export BOOTSTRAP_PYTHON
unset whp_bootstrap_python_value whp_config_line

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

PYTHON_EXPLICIT=0
HOST_PYTHON=
if [ -n "${PYTHON:-}" ]; then
    PYTHON_EXPLICIT=1
    if ! whp_python_usable "$PYTHON"; then
        printf 'error: PYTHON is not Python 3.9 or newer: %s\n' "$PYTHON" >&2
        exit 1
    fi
    HOST_PYTHON=$PYTHON
else
    for python_name in python3 python; do
        python_candidate=$(command -v "$python_name" 2>/dev/null || true)
        if whp_python_usable "$python_candidate"; then
            HOST_PYTHON=$python_candidate
            break
        fi
    done

    # Windows installations may expose only the Python launcher even when a
    # runtime is installed, and Store aliases named python/python3 may exist
    # without being usable from the current MSYS shell. Resolve the launcher to
    # the real interpreter so downstream configure/Meson calls receive an
    # executable path rather than launcher-specific semantics.
    if [ -z "$HOST_PYTHON" ]; then
        case "$(uname -s 2>/dev/null || true)" in
            CYGWIN*|MINGW*|MSYS*)
                python_launcher=$(command -v py 2>/dev/null || true)
                if [ -n "$python_launcher" ]; then
                    python_candidate=$(
                        "$python_launcher" -c 'import sys; print(sys.executable)' \
                            2>/dev/null || true
                    )
                    if whp_python_usable "$python_candidate"; then
                        HOST_PYTHON=$python_candidate
                    fi
                fi
                unset python_launcher
                ;;
        esac
    fi
    unset python_name python_candidate
fi

# menuconfig must remain reachable before Python itself exists. Prefer the
# richer curses UI when a usable host interpreter is already present, but do
# not bootstrap Python merely to enter configuration: the POSIX-shell fallback
# reads and writes the same .whpconfig format.
if [ "${1:-}" = menuconfig ]; then
    shift
    if [ -n "$HOST_PYTHON" ]; then
        exec "$HOST_PYTHON" "$WHP_MENUCONFIG_TOOL" "$WHP_USER_CONFIG" "$@"
    fi
    exec /bin/sh "$WHP_MENUCONFIG_SHELL" "$WHP_USER_CONFIG" "$@"
fi
# Establish one validated seed sed before any bootstrap that needs sed.
# Managed GNU sed cannot occupy this slot because its maintainer-source
# bootstrap requires Automake, while the Python/Automake bootstraps already
# need a basic sed. Keep only the seed identity here; host-tools.sh later
# promotes the pinned GNU sed and exports it through SED/PATH.
if [ -z "${WHP_SED_SEED:-}" ] && [ -n "${SED:-}" ]; then
    WHP_SED_SEED=$SED
fi
WHP_SED_SEED=$("$SOURCE_DIR/sed.sh" --print-seed) || exit 1
export WHP_SED_SEED
printf 'QEMU seed sed: %s\n' "$WHP_SED_SEED" >&2

# Resolve the seed GNU Make once before any bootstrap which consumes it.
# The pinned WHP Make fork is not promoted here yet because its maintainer
# source path still has a Make -> Make bootstrap cycle. MAKE_CMD and MAKE are
# exported together so Python, Automake, Bash, Libtool, libisofs, firmware, and
# the later QEMU stage cannot silently rediscover different Make executables.
. "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"
WHP_MAKE_REQUESTED=${MAKE_CMD:-${MAKE:-}}
if [ -n "$WHP_MAKE_REQUESTED" ]; then
    MAKE_CMD=$(whp_resolve_gnu_make "$WHP_MAKE_REQUESTED" || true)
    if [ -z "$MAKE_CMD" ]; then
        printf '%s\n' \
            "error: MAKE_CMD/MAKE does not identify GNU Make: $WHP_MAKE_REQUESTED" \
            'Set MAKE_CMD or MAKE to a GNU Make executable (often gmake on BSD hosts).' >&2
        exit 1
    fi
else
    MAKE_CMD=$(whp_find_gnu_make || true)
fi
if [ -n "$MAKE_CMD" ]; then
    WHP_MAKE_SEED=$MAKE_CMD
    MAKE=$MAKE_CMD
    export WHP_MAKE_SEED MAKE_CMD MAKE
    printf 'QEMU seed GNU Make: %s\n' "$MAKE_CMD" >&2
fi
unset WHP_MAKE_REQUESTED

# Select a native build-machine C compiler before any compiled fallback can
# run. Target CC is intentionally excluded from this root dependency.
case "$(uname -s 2>/dev/null || true)" in
    CYGWIN*|MINGW*|MSYS*)
        # Python's PCbuild path owns Visual Studio discovery on Windows.
        ;;
    *)
        if [ -z "${WHP_CC_SEED:-}" ] && [ -n "${CC_FOR_BUILD:-}" ]; then
            WHP_CC_SEED=$CC_FOR_BUILD
            export WHP_CC_SEED
        fi
        CC_FOR_BUILD=$("$SOURCE_DIR/cc.sh" --print-cc) || exit 1
        export CC_FOR_BUILD
        printf 'QEMU bootstrap C compiler: %s\n' "$CC_FOR_BUILD" >&2
        ;;
esac

# Explicit PYTHON remains authoritative. Otherwise BOOTSTRAP_PYTHON follows the
# same auto/force/disable policy as the other WHP-managed dependencies:
# auto uses a usable host Python and falls back to the pinned fork, 1 forces
# the fork, and 0 requires a usable host interpreter.
if [ "$PYTHON_EXPLICIT" = 1 ]; then
    PYTHON=$HOST_PYTHON
elif [ "$BOOTSTRAP_PYTHON" = 1 ]; then
    PYTHON=
else
    PYTHON=$HOST_PYTHON
fi

if [ -z "${PYTHON:-}" ]; then
    if [ "$BOOTSTRAP_PYTHON" = 0 ]; then
        printf '%s\n' \
            'error: Python 3.9 or newer is required, but BOOTSTRAP_PYTHON=0 disables the bundled fallback.' \
            'Install Python, set PYTHON, or enable the WHP Python bootstrap.' >&2
        exit 1
    fi
    PYTHON=$(/bin/sh "$SOURCE_DIR/scripts/bootstrap-python.sh") || exit 1
    if ! whp_python_usable "$PYTHON"; then
        printf 'error: bundled WHP Python is not Python 3.9 or newer: %s\n' \
            "${PYTHON:-<missing>}" >&2
        exit 1
    fi
fi

if [ -z "${PYTHON:-}" ]; then
    printf 'error: Python 3.9 or newer is required by QEMU\n' >&2
    exit 1
fi
export PYTHON WHP_USER_CONFIG
unset HOST_PYTHON PYTHON_EXPLICIT

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

# Saved configuration supplies portable policy defaults. Explicit environment
# variables remain one-run overrides and therefore take precedence. Load it
# before selecting Ninja so menuconfig can choose the build executor used by
# both the LLVM bootstrap and QEMU itself.
WHP_CONFIG_ENV=$("$PYTHON" "$WHP_CONFIG_TOOL" --shell "$WHP_USER_CONFIG") || exit 1
eval "$WHP_CONFIG_ENV"
unset WHP_CONFIG_ENV

# Resolve one macOS compiler job budget before compiled dependencies or native
# LLVM start. Explicit JOBS remains authoritative.
if [ "$WHP_HOST_OS" = macos ]; then
    JOBS=$("$PYTHON" "$SOURCE_DIR/scripts/job-budget.py" --print-jobs) || exit 1
    export JOBS
    printf 'WHP macOS compile power: %s (%s jobs)\n' \
        "${MACOS_BUILD_POWER:-balanced}" "$JOBS" >&2
fi

# Host-library helpers are function-only at source time. Load them before the
# host-tool phase so that low-level libraries can be scheduled at their real
# dependency boundary without flattening them into the later QEMU artifact
# library phase.
. "$SOURCE_DIR/scripts/whp-build/host-libraries.sh"

# Keep host-tool bootstraps out of the public entrypoint. This module is sourced
# here so its environment mutations preserve dependency order. It prepares the
# isolated bootstrap-zlib edge before managed Git, while QEMU's artifact zlib,
# SDL, and JACK remain in the later compiler-selected library phase.
. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"

# Parse the LLVM switch before deciding whether QEMU-linked libraries should
# use the seed compiler or the managed LLVM compiler. Portable-core builds do
# not run the native LLVM bootstrap, so when LLVM is disabled the historical
# early preparation path remains available.
BOOTSTRAP_NATIVE_LLVM=$(whp_require_binary_switch BOOTSTRAP_NATIVE_LLVM "${BOOTSTRAP_NATIVE_LLVM:-0}") || exit 1
export BOOTSTRAP_NATIVE_LLVM

if [ "$BOOTSTRAP_NATIVE_LLVM" = 0 ]; then
    whp_prepare_qemu_host_libraries
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

if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then
    NATIVE_LLVM_DIR=$("$WHP_BUILD_BASH" --noprofile --norc \
        "$SOURCE_DIR/scripts/bootstrap-native-clang.sh") || exit 1
    CC="$NATIVE_LLVM_DIR/bin/clang"
    CXX="$NATIVE_LLVM_DIR/bin/clang++"
    AR="${AR:-$NATIVE_LLVM_DIR/bin/llvm-ar}"
    RANLIB="${RANLIB:-$NATIVE_LLVM_DIR/bin/llvm-ranlib}"
    NM="${NM:-$NATIVE_LLVM_DIR/bin/llvm-nm}"
    OBJCOPY="$NATIVE_LLVM_DIR/bin/llvm-objcopy"
    OBJDUMP="$NATIVE_LLVM_DIR/bin/llvm-objdump"
    READELF="$NATIVE_LLVM_DIR/bin/llvm-readelf"
    STRIP="$NATIVE_LLVM_DIR/bin/llvm-strip"
    OBJC="$NATIVE_LLVM_DIR/bin/clang"
    PATH="$NATIVE_LLVM_DIR/bin:$PATH"
    WHP_SHARED_LLVM_DIR="$NATIVE_LLVM_DIR"
    export NATIVE_LLVM_DIR WHP_SHARED_LLVM_DIR CC CXX AR RANLIB NM \
        OBJCOPY OBJDUMP READELF STRIP OBJC PATH

    whp_archive_toolchain_smoke "$CC" "$AR" "$RANLIB" "$BUILD_DIR" "$NM" || exit 1
    WHP_ARCHIVE_TOOL_SIGNATURE="$AR|$RANLIB|$NM"

    # Darwin host links must consume the same LLVM revision that produced the
    # LTO objects. Use the installed Mach-O LLD sibling through Clang's driver;
    # direct LD consumers get the same linker explicitly.
    if [ "$WHP_HOST_OS" = macos ]; then
        LD="$NATIVE_LLVM_DIR/bin/ld64.lld"
        LIPO="$NATIVE_LLVM_DIR/bin/llvm-lipo"
        NATIVE_LLVM_LDFLAG=-fuse-ld=lld
        case " ${LDFLAGS:-} " in
            *" $NATIVE_LLVM_LDFLAG "*) ;;
            *) LDFLAGS="${LDFLAGS:+$LDFLAGS }$NATIVE_LLVM_LDFLAG" ;;
        esac
        export LD LIPO NATIVE_LLVM_LDFLAG LDFLAGS
    fi
    printf 'QEMU native compiler: WHP LLVM (%s)\n' "$NATIVE_LLVM_DIR"
    printf 'QEMU host archiver: %s\n' "$AR"
fi

if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then
    # These libraries are linked into QEMU itself. Build them only after the
    # requested native LLVM toolchain has become the host artifact compiler.
    whp_prepare_qemu_host_libraries
fi

# Publish the canonical configuration shell before Autotools dependencies.
# This preserves the shell contract while still letting native LLVM come first.
unset QEMU_CONFIG_SHELL TOOLCHAIN_CONFIG_SHELL
CONFIG_SHELL="$WHP_BUILD_BASH"
WHP_BUILD_ENTRY_NORMALIZED=1
export WHP_BUILD_BASH CONFIG_SHELL WHP_BUILD_ENTRY_NORMALIZED

# Autotools dependencies must be configured only after the requested native
# LLVM toolchain is available. Otherwise Libtool can cache system ar/ranlib/nm
# before llvm-ar/llvm-ranlib/llvm-nm exist and leak those stale choices into
# libisofs and other downstream projects.
BOOTSTRAP_LIBTOOL=${BOOTSTRAP_LIBTOOL:-auto}
BOOTSTRAP_LIBTOOL=$(whp_normalize_auto_switch BOOTSTRAP_LIBTOOL "$BOOTSTRAP_LIBTOOL") || exit 1
export BOOTSTRAP_LIBTOOL

# GNU Libtool is a host-side Autotools generator used by source dependencies
# such as libisofs.  auto keeps an existing GNU Libtool pair when available
# and otherwise attempts the pinned WHP fork; 1 forces the pinned fork.  Keep
# Apple /usr/bin/libtool out of this path because it is a different tool.
if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "$BOOTSTRAP_LIBTOOL" != 0 ]; then
    LIBTOOL_BOOTSTRAP_MODE=auto
    if [ "$BOOTSTRAP_LIBTOOL" = 1 ]; then
        LIBTOOL_BOOTSTRAP_MODE=force
    fi
    WHP_LIBTOOL_PREFIX=$(
        "$PYTHON" "$SOURCE_DIR/scripts/ensure-libtool.py" \
            --build-dir "$BUILD_DIR" --mode "$LIBTOOL_BOOTSTRAP_MODE"
    ) || exit 1
    unset LIBTOOL_BOOTSTRAP_MODE

    if [ -n "$WHP_LIBTOOL_PREFIX" ]; then
        LIBTOOL="$WHP_LIBTOOL_PREFIX/bin/libtool"
        LIBTOOLIZE="$WHP_LIBTOOL_PREFIX/bin/libtoolize"
        PATH="$WHP_LIBTOOL_PREFIX/bin:$PATH"
        WHP_LIBTOOL_ACLOCAL="$WHP_LIBTOOL_PREFIX/share/aclocal"
        if [ -d "$WHP_LIBTOOL_ACLOCAL" ]; then
            ACLOCAL_PATH="$WHP_LIBTOOL_ACLOCAL${ACLOCAL_PATH:+:$ACLOCAL_PATH}"
            export ACLOCAL_PATH
        fi
        export WHP_LIBTOOL_PREFIX LIBTOOL LIBTOOLIZE PATH

        # Reuse the exact host tools selected while bootstrapping Libtool.
        # This prevents downstream libtoolize users from rediscovering a
        # different archiver/linker suite after the LLVM-first selection.
        WHP_LIBTOOL_MARKER="$WHP_LIBTOOL_PREFIX/.whp-libtool-bootstrap"
        whp_libtool_marker_tool()
        {
            sed -n "s#^$1=\\([^|]*\\)|.*$#\\1#p" "$WHP_LIBTOOL_MARKER" |
                sed -n '1p'
        }
        whp_libtool_marker_value()
        {
            sed -n "s#^$1=##p" "$WHP_LIBTOOL_MARKER" | sed -n '1p'
        }
        AR=$(whp_libtool_marker_tool AR)
        RANLIB=$(whp_libtool_marker_tool RANLIB)
        NM=$(whp_libtool_marker_tool NM)
        OBJDUMP=$(whp_libtool_marker_tool OBJDUMP)
        STRIP=$(whp_libtool_marker_tool STRIP)
        LD=$(whp_libtool_marker_tool LD)
        if grep -q '^ARFLAGS=' "$WHP_LIBTOOL_MARKER"; then
            ARFLAGS=$(whp_libtool_marker_value ARFLAGS)
            AR_FLAGS=$ARFLAGS
            export ARFLAGS AR_FLAGS
        fi
        export AR RANLIB NM OBJDUMP STRIP LD
        if [ "$WHP_HOST_OS" = macos ]; then
            DSYMUTIL=$(whp_libtool_marker_tool DSYMUTIL)
            LIPO=$(whp_libtool_marker_tool LIPO)
            OTOOL=$(whp_libtool_marker_tool OTOOL)
            export DSYMUTIL LIPO OTOOL
        fi
        unset WHP_LIBTOOL_ACLOCAL WHP_LIBTOOL_MARKER
    fi
fi

BOOTSTRAP_LIBISOFS=${BOOTSTRAP_LIBISOFS:-auto}
BOOTSTRAP_LIBISOFS=$(whp_normalize_auto_switch BOOTSTRAP_LIBISOFS "$BOOTSTRAP_LIBISOFS") || exit 1
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

if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then
    # Libtool may select a different archive family. Keep explicit RANLIB/NM
    # wrappers and compatible alternatives rather than enforcing binary paths,
    # but require the exact Clang -> AR -> RANLIB -> NM capability chain to
    # succeed whenever a tool changed. This also rejects wrong-format NM tools.
    whp_archive_tool_signature_now="$AR|$RANLIB|$NM"
    if [ "$whp_archive_tool_signature_now" != "$WHP_ARCHIVE_TOOL_SIGNATURE" ]; then
        whp_archive_toolchain_smoke "$CC" "$AR" "$RANLIB" "$BUILD_DIR" "$NM" || exit 1
    fi
    unset whp_archive_tool_signature_now WHP_ARCHIVE_TOOL_SIGNATURE
fi


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
