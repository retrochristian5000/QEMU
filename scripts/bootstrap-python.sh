#!/bin/sh
set -eu

# build.sh captures stdout to obtain exactly one value: the interpreter path.
# Send bootstrap chatter to stderr and reserve fd 3 for the final path.
exec 3>&1
exec 1>&2

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
SOURCE_DIR=$(CDPATH= cd -- "$SCRIPT_DIR/.." && pwd)
PYTHON_SUBMODULE_PATH=${WHP_PYTHON_SUBMODULE_PATH:-toolchains/python-runtime}
PYTHON_SOURCE_DIR="$SOURCE_DIR/$PYTHON_SUBMODULE_PATH"
PYTHON_BOOTSTRAP_SCHEMA=2
JOBS=${JOBS:-}
cleanup_path=

# This interpreter is a host prerequisite, not a QEMU target object. Never let
# target/guest flags or cross-binutils choices leak into CPython's host build.
unset CC CXX AR AS LD NM RANLIB STRIP
unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS CONFIG_SITE
unset PYTHONHOME PYTHONPATH

cleanup()
{
    if [ -n "$cleanup_path" ]; then
        rm -rf "$cleanup_path"
    fi
}
trap cleanup 0
trap 'exit 1' 1 2 3 15

fail()
{
    printf 'error: %s\n' "$*" >&2
    exit 1
}

require_tool()
{
    command -v "$1" >/dev/null 2>&1 ||
        fail "bundled Python bootstrap dependency not found: $1"
}

python_from_prefix()
{
    prefix=$1
    for candidate in \
        "$prefix/bin/python3" \
        "$prefix/bin/python3.exe" \
        "$prefix/python.exe"; do
        if [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    return 1
}

python_usable()
{
    candidate=$1
    expected_prefix=$2
    [ -n "$candidate" ] || return 1
    "$candidate" -c '
from pathlib import Path
import ensurepip
import sys
import tomllib
import venv
if sys.version_info < (3, 9):
    raise SystemExit(1)
if Path(sys.prefix).resolve() != Path(sys.argv[1]).resolve():
    raise SystemExit(1)
' "$expected_prefix" >/dev/null 2>&1
}

require_tool git
require_tool sed
require_tool mkdir
require_tool rm
require_tool mv
require_tool uname
require_tool dirname
require_tool cat

host_kernel=$(uname -s 2>/dev/null || printf unknown)
host_arch_raw=$(uname -m 2>/dev/null || printf unknown)
case "$host_arch_raw" in
    x86_64|amd64) host_arch=x86_64 ;;
    arm64|aarch64) host_arch=arm64 ;;
    i?86) host_arch=x86 ;;
    *) host_arch=$host_arch_raw ;;
esac
case "$host_kernel" in
    MINGW*|MSYS*) build_mode=pcbuild ;;
    *) build_mode=posix ;;
esac

host_kernel_tag=$(printf '%s' "$host_kernel" | sed 's/[^A-Za-z0-9_.-]/-/g')
host_arch_tag=$(printf '%s' "$host_arch" | sed 's/[^A-Za-z0-9_.-]/-/g')
host_tag="$host_kernel_tag-$host_arch_tag"

if [ -n "${WHP_PYTHON_BOOTSTRAP_DIR:-}" ]; then
    TOOLCHAIN_DIR=$WHP_PYTHON_BOOTSTRAP_DIR
elif [ -n "${XDG_CACHE_HOME:-}" ]; then
    TOOLCHAIN_DIR="$XDG_CACHE_HOME/whp-qemu/python-$host_tag"
elif [ -n "${HOME:-}" ]; then
    case "$host_kernel" in
        Darwin) TOOLCHAIN_DIR="$HOME/Library/Caches/whp-qemu/python-$host_tag" ;;
        *) TOOLCHAIN_DIR="$HOME/.cache/whp-qemu/python-$host_tag" ;;
    esac
else
    TOOLCHAIN_DIR="$SOURCE_DIR/build/toolchains/python-runtime/$host_tag"
fi
case "$TOOLCHAIN_DIR" in
    /*) ;;
    *) fail "bundled Python cache path must be absolute: $TOOLCHAIN_DIR" ;;
esac
WORK_DIR=${WHP_PYTHON_BOOTSTRAP_WORK_DIR:-"${TOOLCHAIN_DIR}.work"}
marker="$TOOLCHAIN_DIR/.whp-python-runtime"

# The QEMU gitlink is the source-of-truth pin. `branch = main` in .gitmodules
# describes where updates come from; builds always use this exact commit.
gitlink=$(git -C "$SOURCE_DIR" ls-tree HEAD -- "$PYTHON_SUBMODULE_PATH" 2>/dev/null || true)
set -- $gitlink
[ "$#" -ge 3 ] || fail "Python runtime gitlink is missing: $PYTHON_SUBMODULE_PATH"
[ "$1" = 160000 ] || fail "Python runtime path is not a gitlink: $PYTHON_SUBMODULE_PATH"
[ "$2" = commit ] || fail "Python runtime gitlink has unexpected type: $2"
python_revision=$3

# Resolve the host compiler policy before checking the cache so a compiler
# upgrade or an explicit compiler change cannot silently reuse an older runtime.
case "$build_mode" in
    posix)
        if [ "$host_kernel" = Darwin ] && command -v xcrun >/dev/null 2>&1; then
            bootstrap_cc=${WHP_PYTHON_BOOTSTRAP_CC:-$(xcrun --sdk macosx --find clang)}
        elif [ -n "${WHP_PYTHON_BOOTSTRAP_CC:-}" ]; then
            bootstrap_cc=$WHP_PYTHON_BOOTSTRAP_CC
        elif [ -n "${CC_FOR_BUILD:-}" ]; then
            bootstrap_cc=$CC_FOR_BUILD
        else
            bootstrap_cc=$(command -v cc 2>/dev/null || command -v clang 2>/dev/null || command -v gcc 2>/dev/null || true)
        fi
        [ -n "$bootstrap_cc" ] || fail 'a host C compiler is required to bootstrap bundled Python'
        command -v "$bootstrap_cc" >/dev/null 2>&1 || [ -x "$bootstrap_cc" ] ||
            fail "bundled Python host C compiler is not executable: $bootstrap_cc"
        bootstrap_cc_version=$("$bootstrap_cc" --version 2>&1 | sed -n '1p')
        [ -n "$bootstrap_cc_version" ] ||
            fail "could not identify bundled Python host C compiler: $bootstrap_cc"
        ;;
    pcbuild)
        # PCbuild owns Visual Studio discovery. Record that policy boundary plus
        # the architecture; the source revision and platform remain separately
        # represented in the marker.
        bootstrap_cc=PCbuild
        bootstrap_cc_version="PCbuild-default-$host_arch"
        ;;
    *) fail "unsupported bundled Python build mode: $build_mode" ;;
esac

expected_marker=$(cat <<EOF
PYTHON_BOOTSTRAP_SCHEMA=$PYTHON_BOOTSTRAP_SCHEMA
PYTHON_GIT_COMMIT=$python_revision
HOST_KERNEL=$host_kernel
HOST_ARCH=$host_arch
BUILD_MODE=$build_mode
BOOTSTRAP_CC=$bootstrap_cc
BOOTSTRAP_CC_VERSION=$bootstrap_cc_version
EOF
)

cached_python=$(python_from_prefix "$TOOLCHAIN_DIR" 2>/dev/null || true)
if [ -f "$marker" ] &&
   [ "$(cat "$marker")" = "$expected_marker" ] &&
   python_usable "$cached_python" "$TOOLCHAIN_DIR"; then
    printf 'Reused bundled WHP Python: %s\n' "$cached_python" >&2
    printf '%s\n' "$cached_python" >&3
    cleanup_path=
    trap - 0
    exit 0
fi

# Cache miss: initialize only the pinned Python submodule, never an unpinned
# clone or a moving remote branch.
git -C "$SOURCE_DIR" submodule update --init --depth 1 "$PYTHON_SUBMODULE_PATH"
actual_revision=$(git -C "$PYTHON_SOURCE_DIR" rev-parse HEAD 2>/dev/null || true)
[ "$actual_revision" = "$python_revision" ] ||
    fail "Python submodule revision mismatch: ${actual_revision:-<missing>} != $python_revision"

parent_dir=$(dirname -- "$TOOLCHAIN_DIR")
mkdir -p "$parent_dir"
rm -rf "$WORK_DIR"
mkdir -p "$WORK_DIR"

case "$build_mode" in
    posix)
        require_tool make
        if [ -n "$JOBS" ]; then
            case "$JOBS" in
                0|*[!0-9]*) fail "JOBS must be a positive integer when set: $JOBS" ;;
            esac
            make_jobs="-j$JOBS"
        else
            make_jobs=
        fi

        if [ "$host_kernel" = Darwin ] && command -v xcrun >/dev/null 2>&1 &&
           [ -z "${SDKROOT:-}" ]; then
            SDKROOT=$(xcrun --sdk macosx --show-sdk-path)
            export SDKROOT
        fi

        # Configure CPython for its final prefix and stage installation with
        # DESTDIR. Moving an interpreter configured for a temporary prefix can
        # leave sysconfig/install metadata referring to the discarded path.
        install_root="$WORK_DIR/install-root.$$"
        rm -rf "$install_root"
        mkdir -p "$install_root"
        staging_dir="$install_root$TOOLCHAIN_DIR"
        cleanup_path=$install_root
        build_dir="$WORK_DIR/build"
        mkdir -p "$build_dir"
        printf 'Bootstrapping WHP Python %s for %s with %s\n' \
            "$python_revision" "$host_tag" "$bootstrap_cc" >&2
        (
            cd "$build_dir"
            CC="$bootstrap_cc" "$PYTHON_SOURCE_DIR/configure" \
                --prefix="$TOOLCHAIN_DIR" \
                --with-ensurepip=install
            if [ -n "$make_jobs" ]; then
                make "$make_jobs"
            else
                make
            fi
            make DESTDIR="$install_root" install
        )
        ;;

    pcbuild)
        require_tool cp
        require_tool cmd.exe
        staging_dir="${TOOLCHAIN_DIR}.new.$$"
        cleanup_path=$staging_dir
        rm -rf "$staging_dir"
        mkdir -p "$staging_dir"
        windows_source="$WORK_DIR/source"
        mkdir -p "$windows_source"
        cp -R "$PYTHON_SOURCE_DIR/." "$windows_source/"
        case "$host_arch" in
            x86_64)
                pc_platform=x64
                pc_dir=amd64
                layout_arch=amd64
                ;;
            x86)
                pc_platform=Win32
                pc_dir=win32
                layout_arch=win32
                ;;
            arm64)
                pc_platform=ARM64
                pc_dir=arm64
                layout_arch=arm64
                ;;
            *) fail "unsupported Windows bundled Python architecture: $host_arch" ;;
        esac
        printf 'Bootstrapping WHP Python %s for Windows %s via PCbuild\n' \
            "$python_revision" "$pc_platform" >&2
        (
            cd "$windows_source/PCbuild"
            cmd.exe /d /s /c "build.bat -p $pc_platform -q"
        )
        built_python="$windows_source/PCbuild/$pc_dir/python.exe"
        [ -x "$built_python" ] ||
            fail "PCbuild did not produce a Python executable: $built_python"
        "$built_python" "$windows_source/PC/layout" \
            --copy "$staging_dir" \
            --source "$windows_source" \
            --build "$windows_source/PCbuild/$pc_dir" \
            --arch "$layout_arch" \
            --preset-default \
            --include-venv \
            --include-pip
        ;;

    *) fail "unsupported bundled Python build mode: $build_mode" ;;
esac

staged_python=$(python_from_prefix "$staging_dir" 2>/dev/null || true)
# POSIX DESTDIR staging intentionally records the final prefix, so it cannot be
# semantically executed until published. Windows layout output is relocatable
# and can be checked before publication.
if [ "$build_mode" = pcbuild ]; then
    python_usable "$staged_python" "$staging_dir" ||
        fail 'staged bundled Python cannot satisfy QEMU Python requirements'
fi
printf '%s\n' "$expected_marker" > "$staging_dir/.whp-python-runtime"

old_dir="${TOOLCHAIN_DIR}.old.$$"
rm -rf "$old_dir"
if [ -e "$TOOLCHAIN_DIR" ]; then
    mv "$TOOLCHAIN_DIR" "$old_dir"
fi
if ! mv "$staging_dir" "$TOOLCHAIN_DIR"; then
    [ ! -e "$old_dir" ] || mv "$old_dir" "$TOOLCHAIN_DIR"
    exit 1
fi
cleanup_path=
rm -rf "$old_dir" "$WORK_DIR"

installed_python=$(python_from_prefix "$TOOLCHAIN_DIR" 2>/dev/null || true)
python_usable "$installed_python" "$TOOLCHAIN_DIR" ||
    fail 'installed bundled Python failed its semantic health check'
printf 'WHP bundled Python ready: %s\n' "$installed_python" >&2
printf '%s\n' "$installed_python" >&3
trap - 0
