#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
script_name=${0##*/}
bash_name=${script_name%.sh}.bash

compiler_has_cache_wrapper()
{
    command_string=${1:-}
    for cache_name in ccache sccache distcc icecc; do
        case " $command_string " in
            *" $cache_name "*|*"/$cache_name "*) return 0 ;;
        esac
    done
    return 1
}

# Compiler caches are build accelerators only. Keep their storage beside the
# build tree and never under PREFIX, so ccache/sccache state cannot become part
# of an installed or packaged QEMU deliverable.
COMPILER_CACHE=${COMPILER_CACHE:-auto}
case "$COMPILER_CACHE" in
    auto|ccache|sccache|none) ;;
    *)
        printf 'error: COMPILER_CACHE must be auto, ccache, sccache, or none: %s\n' \
            "$COMPILER_CACHE" >&2
        exit 1
        ;;
esac

cache_cmd=${WHP_COMPILER_CACHE_CMD:-}
if [ -z "$cache_cmd" ]; then
    case "$COMPILER_CACHE" in
        auto)
            cache_cmd=$(command -v ccache 2>/dev/null || true)
            if [ -z "$cache_cmd" ]; then
                cache_cmd=$(command -v sccache 2>/dev/null || true)
            fi
            ;;
        ccache|sccache)
            cache_cmd=$(command -v "$COMPILER_CACHE" 2>/dev/null || true)
            if [ -z "$cache_cmd" ]; then
                printf 'error: requested compiler cache is not installed: %s\n' \
                    "$COMPILER_CACHE" >&2
                exit 1
            fi
            ;;
        none)
            cache_cmd=
            ;;
    esac
fi

if [ -n "$cache_cmd" ]; then
    case "$cache_cmd" in
        *' '*)
            printf 'error: WHP_COMPILER_CACHE_CMD must name one executable: %s\n' \
                "$cache_cmd" >&2
            exit 1
            ;;
        */*)
            if [ ! -x "$cache_cmd" ]; then
                printf 'error: compiler cache is not executable: %s\n' "$cache_cmd" >&2
                exit 1
            fi
            ;;
        *)
            resolved_cache=$(command -v "$cache_cmd" 2>/dev/null || true)
            if [ -z "$resolved_cache" ]; then
                printf 'error: compiler cache is not executable: %s\n' "$cache_cmd" >&2
                exit 1
            fi
            cache_cmd=$resolved_cache
            unset resolved_cache
            ;;
    esac

    WHP_COMPILER_CACHE_CMD=$cache_cmd
    cache_build_dir=${BUILD_DIR:-$script_dir/build}
    WHP_COMPILER_CACHE_ROOT=${WHP_COMPILER_CACHE_ROOT:-$(dirname -- "$cache_build_dir")/.whp-compiler-cache}
    cache_tag=$(uname -s 2>/dev/null || printf unknown)-$(uname -m 2>/dev/null || printf unknown)
    cache_base=${cache_cmd##*/}
    case "$cache_base" in
        ccache)
            CCACHE_DIR=${CCACHE_DIR:-$WHP_COMPILER_CACHE_ROOT/ccache-$cache_tag}
            export CCACHE_DIR
            ;;
        sccache)
            SCCACHE_DIR=${SCCACHE_DIR:-$WHP_COMPILER_CACHE_ROOT/sccache-$cache_tag}
            export SCCACHE_DIR
            ;;
        *)
            printf 'error: unsupported compiler cache command: %s\n' "$cache_cmd" >&2
            exit 1
            ;;
    esac

    # Preserve raw build-machine compilers before wrapping QEMU's host compiler
    # commands. Firmware/toolchain bootstraps may opt into caching separately.
    CC_FOR_BUILD=${CC_FOR_BUILD:-${CC:-cc}}
    CXX_FOR_BUILD=${CXX_FOR_BUILD:-${CXX:-c++}}
    export CC_FOR_BUILD CXX_FOR_BUILD

    if ! compiler_has_cache_wrapper "${CC:-}"; then
        CC="$cache_cmd ${CC:-cc}"
        export CC
    fi
    if ! compiler_has_cache_wrapper "${CXX:-}"; then
        CXX="$cache_cmd ${CXX:-c++}"
        export CXX
    fi
    export WHP_COMPILER_CACHE_CMD WHP_COMPILER_CACHE_ROOT
    printf 'WHP compiler cache: %s (%s)\n' "$cache_base" "$WHP_COMPILER_CACHE_ROOT" >&2
elif [ "$COMPILER_CACHE" = none ]; then
    # prepare-build.bash still recognizes legacy automatic ccache discovery.
    # Disable ccache itself so the explicit menu choice remains authoritative
    # without making a cache wrapper part of the installed QEMU ABI.
    CCACHE_DISABLE=1
    export CCACHE_DISABLE
    unset WHP_COMPILER_CACHE_CMD
    printf 'WHP compiler cache: disabled\n' >&2
fi

bash_runner=${WHP_BUILD_BASH:-}
if [ -z "$bash_runner" ]; then
    bash_runner=$(command -v bash 2>/dev/null || true)
fi
if [ -z "$bash_runner" ]; then
    printf 'error: GNU Bash is required for %s\n' "$script_name" >&2
    exit 1
fi
exec "$bash_runner" "$script_dir/$bash_name" "$@"
