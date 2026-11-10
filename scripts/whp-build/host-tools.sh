# WHP host bootstrap tool selection.
# Sourced by build.sh after Python, host identity, BUILD_DIR, and .whpconfig are ready.

. "$SOURCE_DIR/scripts/whp-build/shell-functions.sh"

# build.sh selects and logs the host Git seed once, before its early
# source updater (or here, when an opt-out/probe skipped that stage).
# Do not select or log a second Git identity: the initial bootstrap zlib
# must use exactly the same seed as the parent source updater.
if [ "${WHP_GIT_SEED_SELECTED:-0}" != 1 ] ||
   [ -z "${WHP_GIT_SEED:-}" ] || [ ! -x "$WHP_GIT_SEED" ]; then
    printf '%s\n' 'error: QEMU Git seed was not selected before host tools' >&2
    exit 1
fi

# Git needs zlib before native LLVM, but QEMU's zlib must not inherit that
# build-machine compiler. Prepare an isolated bootstrap role here; the artifact
# role is resolved again after compiler promotion.
whp_prepare_bootstrap_zlib

# On macOS, the system is not presumed invalid: auto uses a passing
# host pair and builds the managed fork only when absent or unusable.
# BOOTSTRAP_AUTOMAKE=1 and BOOTSTRAP_AUTOCONF=1 remain explicit force modes.
BOOTSTRAP_AUTOMAKE=$(whp_normalize_auto_switch BOOTSTRAP_AUTOMAKE "${BOOTSTRAP_AUTOMAKE:-auto}") || exit 1
export BOOTSTRAP_AUTOMAKE

# The toolchain binaries may both be GNU while coming from incompatible
# releases. Compare their advertised numeric release, not merely their brand.
# Keep this check POSIX-sh compatible: the host-tool stage precedes managed Bash.
whp_gnu_tool_version()
(
    whp_tool=${1:-}
    whp_family=${2:-}
    [ -n "$whp_tool" ] && [ -x "$whp_tool" ] || exit 1
    whp_banner=$("$whp_tool" --version 2>/dev/null) || exit 1
    whp_line=${whp_banner%%'
'*}
    case "$whp_line" in
        *"($whp_family)"*) ;;
        *) exit 1 ;;
    esac
    whp_version=${whp_line##* }
    case "$whp_version" in
        [0-9]*.[0-9]*)
            case "$whp_version" in *[!0-9.]*|*..*|*.) exit 1 ;; esac ;;
        *) exit 1 ;;
    esac
    printf '%s\\n' "$whp_version"
)

whp_gnu_tool_pair_usable()
{
    whp_pair_version_1=$(whp_gnu_tool_version "$1" "$3") || return 1
    whp_pair_version_2=$(whp_gnu_tool_version "$2" "$3") || return 1
    [ "$whp_pair_version_1" = "$whp_pair_version_2" ]
}

whp_automake_pair_usable()
{
    whp_gnu_tool_pair_usable "$1" "$2" 'GNU automake'
}

# The native Automake seed resolves a coherent automake/aclocal pair and
# accepts explicit WHP_*_SEED choices without requiring another bootstrap.
# Keep the managed Automake phase and its source-cycle guard downstream.
if [ -n "${WHP_AUTOMAKE_SEED:-}" ] || [ -n "${WHP_ACLOCAL_SEED:-}" ]; then
    AUTOMAKE=$(/bin/sh "$SOURCE_DIR/seeds/automake.sh" --print-seed) || exit 1
    ACLOCAL=$(/bin/sh "$SOURCE_DIR/seeds/automake.sh" --print-aclocal) || exit 1
fi

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
    # Seed admission checks GNU identity and paired numeric versions
    # rather than accidentally mixing PATH Automake with another aclocal.
    WHP_HOST_AUTOMAKE=$(/bin/sh "$SOURCE_DIR/seeds/automake.sh" --print-seed 2>/dev/null || true)
    WHP_HOST_ACLOCAL=
    if [ -n "$WHP_HOST_AUTOMAKE" ]; then
        WHP_HOST_ACLOCAL=$(/bin/sh "$SOURCE_DIR/seeds/automake.sh" --print-aclocal 2>/dev/null || true)
    fi
    WHP_NEED_AUTOMAKE=0
    if [ "$BOOTSTRAP_AUTOMAKE" = 1 ]; then
        WHP_NEED_AUTOMAKE=1
    elif [ "$BOOTSTRAP_AUTOMAKE" = auto ]; then
        if ! whp_automake_pair_usable "$WHP_HOST_AUTOMAKE" "$WHP_HOST_ACLOCAL"; then
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
        # Probes intentionally skip expensive bootstraps. Normal force mode
        # must never silently accept the system Automake after a failed pin.
        if [ "$BOOTSTRAP_AUTOMAKE" = 1 ] &&
           [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
           [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
            printf '%s\n' \
                'error: BOOTSTRAP_AUTOMAKE=1 requested the pinned WHP Automake, but its bootstrap failed.' >&2
            exit 1
        elif whp_automake_pair_usable "$WHP_HOST_AUTOMAKE" "$WHP_HOST_ACLOCAL"; then
            AUTOMAKE=$WHP_HOST_AUTOMAKE
            ACLOCAL=$WHP_HOST_ACLOCAL
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
    WHP_AUTOMAKE_BIN_DIR=$(whp_command_dir "$AUTOMAKE")
    PATH="$WHP_AUTOMAKE_BIN_DIR:$PATH"
    export AUTOMAKE ACLOCAL PATH
    printf 'QEMU Automake: %s\n' "$AUTOMAKE" >&2
    unset WHP_AUTOMAKE_BIN_DIR
fi
unset WHP_AUTOMAKE_EXPLICIT

BOOTSTRAP_AUTOCONF=$(whp_normalize_auto_switch BOOTSTRAP_AUTOCONF "${BOOTSTRAP_AUTOCONF:-auto}") || exit 1
export BOOTSTRAP_AUTOCONF

whp_autoconf_pair_usable()
{
    whp_gnu_tool_pair_usable "$1" "$2" 'GNU Autoconf'
}

# A direct autom4te seed is also an Autoconf release contract. Resolve
# both names together before the managed Autoconf stage can replace them.
if [ -n "${WHP_AUTOM4TE_SEED:-}" ] || [ -n "${WHP_AUTOCONF_SEED:-}" ]; then
    AUTOCONF=$(/bin/sh "$SOURCE_DIR/seeds/autom4te.sh" --print-autoconf) || exit 1
    AUTOM4TE=$(/bin/sh "$SOURCE_DIR/seeds/autom4te.sh" --print-seed) || exit 1
fi

WHP_AUTOCONF_EXPLICIT=0
if [ -n "${AUTOCONF:-}" ] || [ -n "${AUTOM4TE:-}" ]; then
    WHP_AUTOCONF_EXPLICIT=1
    if [ -z "${AUTOCONF:-}" ] || [ -z "${AUTOM4TE:-}" ]; then
        printf 'error: AUTOCONF and AUTOM4TE must be supplied as a pair\n' >&2
        exit 1
    fi
    case "$AUTOCONF" in
        */*) ;;
        *) AUTOCONF=$(command -v "$AUTOCONF" 2>/dev/null || true) ;;
    esac
    case "$AUTOM4TE" in
        */*) ;;
        *) AUTOM4TE=$(command -v "$AUTOM4TE" 2>/dev/null || true) ;;
    esac
    if ! whp_autoconf_pair_usable "$AUTOCONF" "$AUTOM4TE"; then
        printf 'error: explicit AUTOCONF/AUTOM4TE pair is not usable\n' >&2
        exit 1
    fi
fi

if [ "$WHP_AUTOCONF_EXPLICIT" != 1 ]; then
    # Do not combine unrelated PATH Autoconf and autom4te executables.
    WHP_HOST_AUTOM4TE=$(/bin/sh "$SOURCE_DIR/seeds/autom4te.sh" --print-seed 2>/dev/null || true)
    WHP_HOST_AUTOCONF=
    if [ -n "$WHP_HOST_AUTOM4TE" ]; then
        WHP_HOST_AUTOCONF=$(/bin/sh "$SOURCE_DIR/seeds/autom4te.sh" --print-autoconf 2>/dev/null || true)
    fi
    WHP_NEED_AUTOCONF=0
    if [ "$BOOTSTRAP_AUTOCONF" = 1 ]; then
        WHP_NEED_AUTOCONF=1
    elif [ "$BOOTSTRAP_AUTOCONF" = auto ]; then
        if ! whp_autoconf_pair_usable "$WHP_HOST_AUTOCONF" "$WHP_HOST_AUTOM4TE"; then
            WHP_NEED_AUTOCONF=1
        fi
    fi

    if [ "$WHP_NEED_AUTOCONF" = 1 ] &&
       [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
       [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
        WHP_AUTOCONF_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-autoconf.py" \
                --build-dir "$BUILD_DIR"
        ) || WHP_AUTOCONF_PREFIX=
        if [ -n "$WHP_AUTOCONF_PREFIX" ]; then
            AUTOCONF="$WHP_AUTOCONF_PREFIX/bin/autoconf"
            AUTOM4TE="$WHP_AUTOCONF_PREFIX/bin/autom4te"
            AUTOHEADER="$WHP_AUTOCONF_PREFIX/bin/autoheader"
            AUTORECONF="$WHP_AUTOCONF_PREFIX/bin/autoreconf"

            # Autoconf embeds its selected GNU M4 path in autom4te.
            # Promote that exact root dependency for later bootstraps
            # instead of letting macOS/Homebrew/PATH rediscover M4.
            WHP_AUTOCONF_MARKER="$WHP_AUTOCONF_PREFIX/.whp-autoconf-bootstrap"
            M4=
            while IFS= read -r WHP_AUTOCONF_MARKER_LINE; do
                case "$WHP_AUTOCONF_MARKER_LINE" in
                    M4_PATH=*)
                        M4=${WHP_AUTOCONF_MARKER_LINE#M4_PATH=}
                        break
                        ;;
                esac
            done < "$WHP_AUTOCONF_MARKER"
            if [ -z "$M4" ] || [ ! -x "$M4" ] ||
               ! "$M4" --gnu --version 2>/dev/null | grep -q 'GNU M4'; then
                printf '%s\n' \
                    'error: managed Autoconf lost its validated GNU M4 dependency.' >&2
                exit 1
            fi
            # Check the promoted executable itself, not merely a GNU-looking
            # version banner.  An unusable M4 must not reach later bootstraps.
            WHP_M4_PROBE=$(
                printf '%s\n' "patsubst(\`ab12cd', \`[0-9]+', \`X')" |
                    "$M4" --gnu --fatal-warnings 2>/dev/null
            ) || WHP_M4_PROBE=
            if [ "$WHP_M4_PROBE" != 'abXcd' ]; then
                printf '%s\n' \
                    'error: managed Autoconf GNU M4 failed its macro execution check.' >&2
                exit 1
            fi
            export M4
            printf 'QEMU GNU M4: %s\n' "$M4" >&2
            unset WHP_AUTOCONF_MARKER WHP_AUTOCONF_MARKER_LINE WHP_M4_PROBE
        fi
    fi

    if ! whp_autoconf_pair_usable "${AUTOCONF:-}" "${AUTOM4TE:-}"; then
        # Keep the same force/probe distinction as the Automake stage.
        if [ "$BOOTSTRAP_AUTOCONF" = 1 ] &&
           [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
           [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
            printf '%s\n' \
                'error: BOOTSTRAP_AUTOCONF=1 requested the pinned WHP Autoconf, but its bootstrap failed.' >&2
            exit 1
        elif whp_autoconf_pair_usable "$WHP_HOST_AUTOCONF" "$WHP_HOST_AUTOM4TE"; then
            AUTOCONF=$WHP_HOST_AUTOCONF
            AUTOM4TE=$WHP_HOST_AUTOM4TE
        else
            AUTOCONF=
            AUTOM4TE=
            printf '%s\n' \
                'WHP Autoconf unavailable; later maintainer-source bootstraps may fail.' >&2
        fi
    fi
    unset WHP_HOST_AUTOCONF WHP_HOST_AUTOM4TE WHP_NEED_AUTOCONF WHP_AUTOCONF_PREFIX
fi

if [ -n "${AUTOCONF:-}" ]; then
    WHP_AUTOCONF_BIN_DIR=$(whp_command_dir "$AUTOCONF")
    if [ -z "${AUTOHEADER:-}" ] && [ -x "$WHP_AUTOCONF_BIN_DIR/autoheader" ]; then
        AUTOHEADER="$WHP_AUTOCONF_BIN_DIR/autoheader"
    fi
    if [ -z "${AUTORECONF:-}" ] && [ -x "$WHP_AUTOCONF_BIN_DIR/autoreconf" ]; then
        AUTORECONF="$WHP_AUTOCONF_BIN_DIR/autoreconf"
    fi
    PATH="$WHP_AUTOCONF_BIN_DIR:$PATH"
    export AUTOCONF AUTOM4TE AUTOHEADER AUTORECONF PATH
    printf 'QEMU Autoconf: %s\n' "$AUTOCONF" >&2
    unset WHP_AUTOCONF_BIN_DIR
fi
unset WHP_AUTOCONF_EXPLICIT


# AWK is a pre-Python root; preserve it for source configuration and build
# the pinned Gawk fork only after the Autotools source generators are ready.
# Do not require managed Gawk to generate itself. A passing managed binary
# replaces literal awk (through the existing locked shim) and $AWK together.
BOOTSTRAP_GAWK=$(whp_normalize_auto_switch BOOTSTRAP_GAWK "${BOOTSTRAP_GAWK:-auto}") || exit 1
export BOOTSTRAP_GAWK

WHP_HOST_AWK_FOR_BOOTSTRAP=${WHP_AWK_BOOTSTRAP_SEED:-${WHP_AWK_SEED:-}}
if [ "$BOOTSTRAP_GAWK" != 0 ] &&
   [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_BUILD_DIR_PROBE_ONLY:-0}" != 1 ] &&
   [ "$WHP_HOST_OS" != windows ]; then
    if [ "$BOOTSTRAP_GAWK" = 1 ] || [ "$WHP_HOST_OS" = macos ]; then
        WHP_GAWK_CMD=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-gawk.py" --build-dir "$BUILD_DIR"
        ) || WHP_GAWK_CMD=
        if [ -n "$WHP_GAWK_CMD" ] && [ -x "$WHP_GAWK_CMD" ]; then
            # The helper validates GNU Awk's native execution and semantic
            # behavior before promotion. Keep the old binary as root seed.
            WHP_AWK_BOOTSTRAP_SEED=$WHP_HOST_AWK_FOR_BOOTSTRAP
            WHP_AWK_SEED=$WHP_GAWK_CMD
            AWK=$WHP_GAWK_CMD
            WHP_AWK_LOCKED=1
            export WHP_AWK_BOOTSTRAP_SEED WHP_AWK_SEED WHP_AWK_LOCKED AWK
            printf 'QEMU managed Gawk: %s (root seed %s)\\n' \\
                "$AWK" "$WHP_AWK_BOOTSTRAP_SEED" >&2
        elif [ "$BOOTSTRAP_GAWK" = 1 ]; then
            printf '%s\\n' \\
                'error: BOOTSTRAP_GAWK=1 requires a passing pinned Gawk build.' >&2
            exit 1
        else
            printf 'WHP managed Gawk unavailable; retaining native AWK seed: %s\\n' \\
                "$WHP_HOST_AWK_FOR_BOOTSTRAP" >&2
        fi
        unset WHP_GAWK_CMD
    fi
fi
unset WHP_HOST_AWK_FOR_BOOTSTRAP

BOOTSTRAP_MAKE=$(whp_normalize_auto_switch BOOTSTRAP_MAKE "${BOOTSTRAP_MAKE:-auto}") || exit 1
export BOOTSTRAP_MAKE

# Keep the first GNU Make as an explicit seed through Python and the
# maintainer Automake/Autoconf stages. After those inputs exist, macOS auto
# mode prefers the pinned WHP Make while force mode requires it everywhere.
WHP_PROMOTE_MAKE=0
if [ "$BOOTSTRAP_MAKE" = 1 ]; then
    WHP_PROMOTE_MAKE=1
elif [ "$BOOTSTRAP_MAKE" = auto ] && [ "$WHP_HOST_OS" = macos ]; then
    WHP_PROMOTE_MAKE=1
fi

if [ "$WHP_PROMOTE_MAKE" = 1 ] &&
   [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
   [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ] &&
   [ "$WHP_HOST_OS" != windows ]; then
    if [ -z "${WHP_MAKE_SEED:-}" ]; then
        if [ "$BOOTSTRAP_MAKE" = 1 ]; then
            printf '%s\n' 'error: BOOTSTRAP_MAKE=1 requires a seed GNU Make.' >&2
            exit 1
        fi
    else
        WHP_MAKE_PREFIX=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-make.py" --build-dir "$BUILD_DIR"
        ) || WHP_MAKE_PREFIX=
        if [ -n "$WHP_MAKE_PREFIX" ]; then
            MAKE_CMD=$(whp_resolve_gnu_make "$WHP_MAKE_PREFIX/bin/make" || true)
        else
            MAKE_CMD=
        fi
        if [ -n "$MAKE_CMD" ]; then
            MAKE=$MAKE_CMD
            WHP_MAKE_BIN_DIR=$(whp_command_dir "$MAKE_CMD")
            PATH="$WHP_MAKE_BIN_DIR:$PATH"
            export WHP_MAKE_PREFIX MAKE_CMD MAKE PATH
            printf 'QEMU make: WHP managed %s\n' \
                "$("$MAKE_CMD" --version 2>/dev/null | sed -n '1p')" >&2
            unset WHP_MAKE_BIN_DIR
        elif [ "$BOOTSTRAP_MAKE" = 1 ]; then
            printf '%s\n' 'error: BOOTSTRAP_MAKE=1 requested the pinned WHP GNU Make, but its bootstrap failed.' >&2
            exit 1
        else
            MAKE_CMD=$WHP_MAKE_SEED
            MAKE=$MAKE_CMD
            export MAKE_CMD MAKE
            printf 'QEMU make: managed bootstrap unavailable; retaining seed: %s\n' "$MAKE_CMD" >&2
        fi
        unset WHP_MAKE_PREFIX
    fi
fi
unset WHP_PROMOTE_MAKE

BOOTSTRAP_SED=$(whp_normalize_auto_switch BOOTSTRAP_SED "${BOOTSTRAP_SED:-auto}") || exit 1
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
    WHP_HOST_SED=$("$SOURCE_DIR/seeds/sed.sh" --print-seed 2>/dev/null || true)
    if ! whp_sed_usable "$WHP_HOST_SED"; then
        printf 'error: QEMU sed.sh could not resolve a working host sed seed\n' >&2
        exit 1
    fi
    # build.sh published the seed before Python. Do not erase that identity
    # merely because the managed GNU sed executable was promoted for $SED.
    if [ -z "${WHP_SED_SEED:-}" ]; then
        WHP_SED_SEED=$WHP_HOST_SED
        export WHP_SED_SEED
    fi

    SED=
    if [ "$BOOTSTRAP_SED" != 1 ] && whp_sed_is_gnu "$WHP_HOST_SED"; then
        SED=$WHP_HOST_SED
    elif [ "$BOOTSTRAP_SED" != 0 ] &&
         [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ] &&
         [ "${WHP_PORTABLE_PROBE_ONLY:-0}" != 1 ]; then
        SED=$(
            "$PYTHON" "$SOURCE_DIR/scripts/ensure-sed.py" --build-dir "$BUILD_DIR"
        ) || SED=
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

WHP_SED_DIR=$(whp_command_dir "$SED")
PATH="$WHP_SED_DIR:$PATH"
export SED PATH
if whp_sed_is_gnu "$SED"; then
    WHP_SED_KIND=GNU
else
    WHP_SED_KIND=host
fi
printf 'QEMU sed: %s (%s)\n' "$SED" "$WHP_SED_KIND" >&2
unset WHP_SED_DIR WHP_SED_KIND

BOOTSTRAP_GIT=$(whp_normalize_auto_switch BOOTSTRAP_GIT "${BOOTSTRAP_GIT:-auto}") || exit 1
export BOOTSTRAP_GIT

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

# A reduced local-only WHP Git cannot fetch HTTPS dependencies.
# Bind the already-validated seed when no full managed Git or caller-selected
# Git was promoted. Avoid an untracked PATH fallback in the DTC updater.
if [ -z "${GIT:-}" ]; then
    GIT="$WHP_GIT_SEED"
    export GIT
    printf 'QEMU Git: verified seed %s (%s)\n' \
        "$GIT" "$("$GIT" --version 2>/dev/null || printf unknown)" >&2
fi

# The public launcher defers its Git-dependent cache stage until the
# finalized Git executable is available. This reconciles initialized source
# once and builds optional sccache before Ninja/Bash source compilation.
# Standalone host-tool fixtures without this callback remain usable.
if command -v whp_prepare_git_dependent_cache >/dev/null 2>&1; then
    whp_prepare_git_dependent_cache || exit 1
fi

# Ninja is a small, independent C++ host tool. After selecting Git,
# prepare it before the larger Bash source build; it needs Python and a
# native C++ compiler, not a managed Bash or Autotools environment.
BOOTSTRAP_NINJA=$(whp_normalize_auto_switch BOOTSTRAP_NINJA "${BOOTSTRAP_NINJA:-auto}") || exit 1
export BOOTSTRAP_NINJA

# An explicit Ninja path is a command contract, not a hint to be accepted
# before the next CMake/Meson stage. Resolve and probe it at this boundary.
whp_ninja_command_usable()
{
    [ -n "${1:-}" ] || return 1
    case "$1" in
        */*) whp_ninja_candidate=$1 ;;
        *) whp_ninja_candidate=$(command -v "$1" 2>/dev/null) || return 1 ;;
    esac
    [ -f "$whp_ninja_candidate" ] && [ -x "$whp_ninja_candidate" ] || return 1
    whp_ninja_version=$("$whp_ninja_candidate" --version 2>/dev/null) || return 1
    [ -n "$whp_ninja_version" ] || return 1
    NINJA_CMD=$whp_ninja_candidate
}

# QEMU's normal Meson path needs Ninja before configuration, not only when the
# final build command is launched. An explicit NINJA_CMD is authoritative.
# On macOS, auto prefers the pinned WHP Ninja so the process-launch fast path
# is used even when Homebrew Ninja is installed; it falls back to a host Ninja
# if the optional bundled bootstrap is unavailable. Other hosts keep the
# host-first auto policy. 1 forces the pinned fork, and 0 requires a host Ninja.
# Export NINJA as well as NINJA_CMD so QEMU/Meson and WHP helpers consume one
# exact executable.
if [ "${WHP_SHELL_PROBE_ONLY:-0}" != 1 ]; then
    if [ -n "${NINJA_CMD:-}" ]; then
        if [ "$BOOTSTRAP_NINJA" = 1 ]; then
            printf '%s\n' 'error: BOOTSTRAP_NINJA=1 conflicts with explicit NINJA_CMD.' >&2
            exit 1
        fi
        if ! whp_ninja_command_usable "$NINJA_CMD"; then
            printf 'error: NINJA_CMD is not a runnable Ninja command: %s\n' "$NINJA_CMD" >&2
            exit 1
        fi
    fi
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
    if [ -n "${NINJA_CMD:-}" ] &&
       ! whp_ninja_command_usable "$NINJA_CMD"; then
        NINJA_CMD=
    fi
    if [ -z "${NINJA_CMD:-}" ] && [ "$BOOTSTRAP_NINJA" != 0 ] && \
       [ "$WHP_BUNDLED_NINJA_TRIED" != 1 ]; then
        NINJA_CMD=$("$PYTHON" "$SOURCE_DIR/scripts/ensure-ninja.py" \
            --build-dir "$BUILD_DIR") || exit 1
    fi
    if [ -n "${NINJA_CMD:-}" ] &&
       ! whp_ninja_command_usable "$NINJA_CMD"; then
        NINJA_CMD=
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
            NINJA_DIR=$(whp_command_dir "$NINJA_CMD")
            PATH="$NINJA_DIR:$PATH"
            unset NINJA_DIR
            ;;
    esac
    # The bundled Ninja supports a bounded *automatic* job count, which
    # protects ad-hoc Meson/Ninja calls lacking -j.  Explicit -j remains
    # authoritative, and host/system Ninja is not assigned a new policy.
    case "$NINJA_CMD" in
        */.whp-host-tools/ninja-*/ninja|*/.whp-host-tools/ninja-*/ninja.exe)
            NINJA_AUTO_JOBS=${NINJA_AUTO_JOBS:-2}
            export NINJA_AUTO_JOBS
            ;;
    esac
    NINJA=$NINJA_CMD
    export NINJA_CMD NINJA PATH
fi

BOOTSTRAP_BASH=$(whp_normalize_auto_switch BOOTSTRAP_BASH "${BOOTSTRAP_BASH:-auto}") || exit 1
export BOOTSTRAP_BASH

whp_bash_usable()
{
    [ -n "${1:-}" ] || return 1
    [ -x "$1" ] || return 1
    # --noprofile/--norc do NOT suppress BASH_ENV in noninteractive shells.
    # Use one clean startup environment for version and required LLVM/WHP
    # build features; prevent unrelated user hooks from causing false misses.
    env -u BASH_ENV -u ENV -u POSIXLY_CORRECT -u SHELLOPTS -u BASHOPTS \
        "$1" --noprofile --norc -c '
        test -n "${BASH_VERSION:-}" || exit 1
        (( BASH_VERSINFO[0] > 3 ||
           (BASH_VERSINFO[0] == 3 && BASH_VERSINFO[1] >= 2) )) || exit 1
        whp_probe_array=(one two)
        [[ "${#whp_probe_array[@]}" -eq 2 ]] || exit 1
        (( whp_probe_value = 1 + 1 ))
        [[ "$whp_probe_value" -eq 2 ]] || exit 1
        IFS= read -r whp_probe_line < <(printf "%s\\n" process-substitution)
        [[ "$whp_probe_line" == process-substitution ]] || exit 1
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

