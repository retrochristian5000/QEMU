# WHP host bootstrap tool selection.
# Sourced by build.sh after Python, host identity, BUILD_DIR, and .whpconfig are ready.

BOOTSTRAP_AUTOMAKE=${BOOTSTRAP_AUTOMAKE:-auto}
case "$BOOTSTRAP_AUTOMAKE" in
    y) BOOTSTRAP_AUTOMAKE=1 ;;
    n) BOOTSTRAP_AUTOMAKE=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_AUTOMAKE must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_AUTOMAKE

whp_automake_pair_usable()
{
    [ -n "${1:-}" ] && [ -x "$1" ] || return 1
    [ -n "${2:-}" ] && [ -x "$2" ] || return 1
    "$1" --version 2>/dev/null | grep -q 'GNU automake' || return 1
    "$2" --version 2>/dev/null | grep -q 'GNU automake'
}

WHP_AUTOMAKE_EXPLICIT=0
if [ -n "${AUTOMAKE:-}" ] || [ -n "${ACLOCAL:-}" ]; then
    WHP_AUTOMAKE_EXPLICIT=1
    if [ -z "${AUTOMAKE:-}" ] || [ -z "${ACLOCAL:-}" ]; then
        printf 'error: AUTOMAKE and ACLOCAL must be supplied as a pair\n' >&2
        exit 1
    fi
    case "$AUTOMAKE" in
        */*) ;;
        *) AUTOMAKE=$(command -v "$AUTOMAKE" 2>/dev/null || true) ;;
    esac
    case "$ACLOCAL" in
        */*) ;;
        *) ACLOCAL=$(command -v "$ACLOCAL" 2>/dev/null || true) ;;
    esac
    if ! whp_automake_pair_usable "$AUTOMAKE" "$ACLOCAL"; then
        printf 'error: explicit AUTOMAKE/ACLOCAL pair is not usable\n' >&2
        exit 1
    fi
fi

if [ "$WHP_AUTOMAKE_EXPLICIT" != 1 ]; then
    WHP_HOST_AUTOMAKE=$(command -v automake 2>/dev/null || true)
    WHP_HOST_ACLOCAL=$(command -v aclocal 2>/dev/null || true)
    WHP_NEED_AUTOMAKE=0
    if [ "$BOOTSTRAP_AUTOMAKE" = 1 ]; then
        WHP_NEED_AUTOMAKE=1
    elif [ "$BOOTSTRAP_AUTOMAKE" = auto ]; then
        if [ "$WHP_HOST_OS" = macos ] ||
           ! whp_automake_pair_usable "$WHP_HOST_AUTOMAKE" "$WHP_HOST_ACLOCAL"; then
            WHP_NEED_AUTOMAKE=1
        fi
    fi

    if [ "$WHP_NEED_AUTOMAKE" = 1 ] &&
       [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
        WHP_AUTOMAKE_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-automake.py" \
                --build-dir "$BUILD_DIR"
        ) || WHP_AUTOMAKE_PREFIX=
        if [ -n "$WHP_AUTOMAKE_PREFIX" ]; then
            AUTOMAKE="$WHP_AUTOMAKE_PREFIX/bin/automake"
            ACLOCAL="$WHP_AUTOMAKE_PREFIX/bin/aclocal"
        fi
    fi

    if ! whp_automake_pair_usable "${AUTOMAKE:-}" "${ACLOCAL:-}"; then
        if whp_automake_pair_usable "$WHP_HOST_AUTOMAKE" "$WHP_HOST_ACLOCAL"; then
            AUTOMAKE=$WHP_HOST_AUTOMAKE
            ACLOCAL=$WHP_HOST_ACLOCAL
        elif [ "$BOOTSTRAP_AUTOMAKE" = 1 ]; then
            printf '%s\n' \
                'error: BOOTSTRAP_AUTOMAKE=1 requested the pinned WHP Automake, but its bootstrap failed.' >&2
            exit 1
        else
            AUTOMAKE=
            ACLOCAL=
            printf '%s\n' \
                'WHP Automake unavailable; later Autotools source bootstraps may fall back or fail.' >&2
        fi
    fi
    unset WHP_HOST_AUTOMAKE WHP_HOST_ACLOCAL WHP_NEED_AUTOMAKE WHP_AUTOMAKE_PREFIX
fi

if [ -n "${AUTOMAKE:-}" ]; then
    WHP_AUTOMAKE_BIN_DIR=$(dirname -- "$AUTOMAKE")
    PATH="$WHP_AUTOMAKE_BIN_DIR:$PATH"
    export AUTOMAKE ACLOCAL PATH
    printf 'QEMU Automake: %s\n' "$AUTOMAKE" >&2
    unset WHP_AUTOMAKE_BIN_DIR
fi
unset WHP_AUTOMAKE_EXPLICIT

BOOTSTRAP_SED=${BOOTSTRAP_SED:-auto}
case "$BOOTSTRAP_SED" in
    y) BOOTSTRAP_SED=1 ;;
    n) BOOTSTRAP_SED=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_SED must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_SED

whp_sed_usable()
{
    [ -n "${1:-}" ] || return 1
    [ -x "$1" ] || return 1
    [ "$(printf 'alpha\n' | "$1" -n 's/^alpha$/beta/p' 2>/dev/null)" = beta ]
}

whp_sed_is_gnu()
{
    whp_sed_usable "$1" || return 1
    "$1" --version 2>/dev/null | grep -q 'GNU sed'
}

# GNU sed's Git bootstrap itself uses sed.  Therefore the system sed is a
# deliberately small seed boundary: once Python is available, auto keeps an
# existing GNU sed or tries the pinned WHP fork.  The validated result is then
# exported through both SED and PATH so literal 'sed' calls and Autoconf agree.
if [ -n "${SED:-}" ]; then
    case "$SED" in
        *[[:space:]]*)
            printf 'error: SED must name one executable: %s\n' "$SED" >&2
            exit 1
            ;;
    esac
    case "$SED" in
        */*) WHP_SED_EXPLICIT=$SED ;;
        *) WHP_SED_EXPLICIT=$(command -v "$SED" 2>/dev/null || true) ;;
    esac
    if ! whp_sed_usable "$WHP_SED_EXPLICIT"; then
        printf 'error: SED is not a usable sed executable: %s\n' "$SED" >&2
        exit 1
    fi
    SED=$WHP_SED_EXPLICIT
    unset WHP_SED_EXPLICIT
else
    WHP_HOST_SED=$("$SOURCE_DIR/sed.sh" --print-seed 2>/dev/null || true)
    if ! whp_sed_usable "$WHP_HOST_SED"; then
        printf 'error: QEMU sed.sh could not resolve a working host sed seed\n' >&2
        exit 1
    fi

    SED=
    if [ "$BOOTSTRAP_SED" != 1 ] && whp_sed_is_gnu "$WHP_HOST_SED"; then
        SED=$WHP_HOST_SED
    elif [ "$BOOTSTRAP_SED" != 0 ] &&
         [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
         [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
        WHP_SED_SEED=$WHP_HOST_SED
        export WHP_SED_SEED
        SED=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-sed.py" --build-dir "$BUILD_DIR"
        ) || SED=
        unset WHP_SED_SEED
    fi

    if [ -z "$SED" ]; then
        if [ "$BOOTSTRAP_SED" = 1 ]; then
            printf '%s\n'                 'error: BOOTSTRAP_SED=1 requested the pinned GNU sed, but its bootstrap failed.' >&2
            exit 1
        fi
        SED=$WHP_HOST_SED
        if [ "$BOOTSTRAP_SED" = auto ] && ! whp_sed_is_gnu "$SED"; then
            printf 'WHP GNU sed bootstrap unavailable; retaining host seed sed: %s\n'                 "$SED" >&2
        fi
    fi
    unset WHP_HOST_SED
fi

WHP_SED_DIR=$(dirname -- "$SED")
PATH="$WHP_SED_DIR:$PATH"
export SED PATH
if whp_sed_is_gnu "$SED"; then
    WHP_SED_KIND=GNU
else
    WHP_SED_KIND=host
fi
printf 'QEMU sed: %s (%s)\n' "$SED" "$WHP_SED_KIND" >&2
unset WHP_SED_DIR WHP_SED_KIND

BOOTSTRAP_GIT=${BOOTSTRAP_GIT:-auto}
case "$BOOTSTRAP_GIT" in
    y) BOOTSTRAP_GIT=1 ;;
    n) BOOTSTRAP_GIT=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_GIT must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_GIT

WHP_GIT_SEED=$("$SOURCE_DIR/git.sh" --print-seed 2>/dev/null || true)
if [ -z "$WHP_GIT_SEED" ]; then
    printf 'error: QEMU git.sh could not resolve a usable bootstrap Git\n' >&2
    exit 1
fi
export WHP_GIT_SEED

if [ "$BOOTSTRAP_GIT" != 0 ] &&
   [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "$WHP_HOST_OS" != windows ]; then
    WHP_GIT_MODE=auto
    [ "$BOOTSTRAP_GIT" != 1 ] || WHP_GIT_MODE=force
    WHP_GIT_PREFIX=$(
        "$PYTHON" "$SOURCE_DIR/scripts/ensure-git.py" \
            --build-dir "$BUILD_DIR" --mode "$WHP_GIT_MODE"
    ) || WHP_GIT_PREFIX=
    unset WHP_GIT_MODE

    if [ -n "$WHP_GIT_PREFIX" ] && [ -x "$WHP_GIT_PREFIX/bin/git" ]; then
        WHP_MANAGED_GIT="$WHP_GIT_PREFIX/bin/git"
        WHP_GIT_EXEC_PATH=$("$WHP_MANAGED_GIT" --exec-path 2>/dev/null || true)
        if [ -n "$WHP_GIT_EXEC_PATH" ] &&
           [ -x "$WHP_GIT_EXEC_PATH/git-remote-https" ]; then
            GIT="$WHP_MANAGED_GIT"
            PATH="$WHP_GIT_PREFIX/bin:$PATH"
            export GIT WHP_GIT_PREFIX PATH
            printf 'QEMU Git: WHP managed %s\n' \
                "$("$GIT" --version 2>/dev/null || printf unknown)" >&2
        else
            WHP_GIT_LOCAL="$WHP_MANAGED_GIT"
            export WHP_GIT_LOCAL WHP_GIT_PREFIX
            printf 'QEMU Git: WHP local profile %s; seed remains network authority\n' \
                "$("$WHP_GIT_LOCAL" --version 2>/dev/null || printf unknown)" >&2
            if [ "$BOOTSTRAP_GIT" = 1 ]; then
                printf '%s\n' \
                    'error: BOOTSTRAP_GIT=1 requires managed Git with HTTPS transport' >&2
                exit 1
            fi
        fi
        unset WHP_MANAGED_GIT WHP_GIT_EXEC_PATH
    elif [ "$BOOTSTRAP_GIT" = 1 ]; then
        printf '%s\n' \
            'error: BOOTSTRAP_GIT=1 requested the pinned WHP Git, but its bootstrap failed.' >&2
        exit 1
    fi
fi

BOOTSTRAP_BASH=${BOOTSTRAP_BASH:-auto}
case "$BOOTSTRAP_BASH" in
    y) BOOTSTRAP_BASH=1 ;;
    n) BOOTSTRAP_BASH=0 ;;
    auto|0|1) ;;
    *)
        printf 'error: BOOTSTRAP_BASH must be auto, 0, or 1\n' >&2
        exit 1
        ;;
esac
export BOOTSTRAP_BASH

whp_bash_usable()
{
    [ -n "${1:-}" ] || return 1
    [ -x "$1" ] || return 1
    "$1" --noprofile --norc -c '
        test -n "${BASH_VERSION:-}" || exit 1
        test "${BASH_VERSINFO[0]}" -gt 3 ||
            { test "${BASH_VERSINFO[0]}" -eq 3 &&
              test "${BASH_VERSINFO[1]}" -ge 2; }
    ' >/dev/null 2>&1
}

if [ -z "$WHP_BUILD_BASH" ]; then
    if [ "$WHP_HOST_OS" = macos ] && [ -x /bin/bash ]; then
        WHP_BUILD_BASH=/bin/bash
    else
        WHP_BUILD_BASH=$(command -v bash 2>/dev/null || true)
    fi
fi

if [ "$WHP_BUILD_BASH_EXPLICIT" != 1 ] &&
   [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_FORCE_PORTABLE_CORE:-0}" != 1 ]; then
    WHP_BOOTSTRAP_BASH=0
    if [ "$BOOTSTRAP_BASH" = 1 ]; then
        WHP_BOOTSTRAP_BASH=1
    elif [ "$BOOTSTRAP_BASH" = auto ]; then
        if [ "$WHP_HOST_OS" = macos ] || ! whp_bash_usable "$WHP_BUILD_BASH"; then
            WHP_BOOTSTRAP_BASH=1
        fi
    fi

    if [ "$WHP_BOOTSTRAP_BASH" = 1 ]; then
        WHP_BUNDLED_BASH=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-bash.py" --build-dir "$BUILD_DIR"
        ) || WHP_BUNDLED_BASH=
        if whp_bash_usable "$WHP_BUNDLED_BASH"; then
            WHP_BUILD_BASH=$WHP_BUNDLED_BASH
        elif [ "$BOOTSTRAP_BASH" = 1 ]; then
            printf '%s\n' \
                'error: BOOTSTRAP_BASH=1 requested the pinned WHP Bash, but its bootstrap failed.' >&2
            exit 1
        elif ! whp_bash_usable "$WHP_BUILD_BASH"; then
            WHP_BUILD_BASH=
        fi
        unset WHP_BUNDLED_BASH
    fi
    unset WHP_BOOTSTRAP_BASH
fi

# Publish the selected implementation shell before any managed Autotools
# dependency is bootstrapped. The Libtool bootstrap otherwise defaults
# CONFIG_SHELL to /bin/sh and can silently escape the WHP shell policy.
if [ -n "$WHP_BUILD_BASH" ]; then
    CONFIG_SHELL="$WHP_BUILD_BASH"
    export WHP_BUILD_BASH CONFIG_SHELL
fi

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
