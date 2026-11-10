#!/bin/sh
set -eu

case "$0" in
    */*) whp_entry_dir=${0%/*}; [ -n "$whp_entry_dir" ] || whp_entry_dir=/ ;;
    *) whp_entry_dir=. ;;
esac
script_dir=$(CDPATH= cd -- "$whp_entry_dir" && pwd)
unset whp_entry_dir

# Direct calls must enter through the public policy boundary first.
if [ "${WHP_BUILD_ENTRY_NORMALIZED:-0}" != 1 ]; then
    exec "$script_dir/build.sh" "$@"
fi
script_name=${0##*/}
bash_name=${script_name%.sh}.bash

# Only a leading compiler launcher is a cache wrapper. A flag or compiler
# argument mentioning "sccache" is not evidence that CC/CXX is wrapped.
compiler_cache_wrapper_name()
{
    case "${1:-}" in
        ccache\ *|*/ccache\ *) printf '%s\\n' ccache ;;
        sccache\ *|*/sccache\ *) printf '%s\\n' sccache ;;
        distcc\ *|*/distcc\ *) printf '%s\\n' distcc ;;
        icecc\ *|*/icecc\ *) printf '%s\\n' icecc ;;
    esac
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
# Inherited cache state is not authority over this invocation's selection.
if [ -n "$cache_cmd" ]; then
    if [ "$COMPILER_CACHE" = none ]; then
        printf 'error: COMPILER_CACHE=none conflicts with WHP_COMPILER_CACHE_CMD\n' >&2
        exit 1
    fi
    if [ "$COMPILER_CACHE" != auto ] &&
       [ "${cache_cmd##*/}" != "$COMPILER_CACHE" ]; then
        printf 'error: COMPILER_CACHE=%s conflicts with WHP_COMPILER_CACHE_CMD=%s\n' \
            "$COMPILER_CACHE" "$cache_cmd" >&2
        exit 1
    fi
fi
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
    case "$cache_build_dir" in
        */*) cache_parent=${cache_build_dir%/*}; [ -n "$cache_parent" ] || cache_parent=/ ;;
        *) cache_parent=. ;;
    esac
    WHP_COMPILER_CACHE_ROOT=${WHP_COMPILER_CACHE_ROOT:-$cache_parent/.whp-compiler-cache}
    unset cache_parent
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
            . "$script_dir/scripts/whp-build/sccache-policy.sh"
            whp_sccache_memory_policy
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

    cc_cache_wrapper=$(compiler_cache_wrapper_name "${CC:-}")
    cxx_cache_wrapper=$(compiler_cache_wrapper_name "${CXX:-}")
    for inherited_wrapper in "$cc_cache_wrapper" "$cxx_cache_wrapper"; do
        if [ -n "$inherited_wrapper" ] && [ "$inherited_wrapper" != "$cache_base" ]; then
            printf 'error: selected %s cache conflicts with compiler launcher %s\\n' \\
                "$cache_base" "$inherited_wrapper" >&2
            exit 1
        fi
        if [ -n "$inherited_wrapper" ] && [ "${WHP_MANAGED_SCCACHE:-0}" = 1 ]; then
            # Managed sccache has fork-specific PCH guarantees. Do not accept
            # an inherited, potentially different sccache binary as equivalent.
            printf '%s\\n' 'error: managed sccache requires unwrapped CC/CXX compiler commands' >&2
            exit 1
        fi
    done
    unset inherited_wrapper
    if [ -z "$cc_cache_wrapper" ]; then
        CC="$cache_cmd ${CC:-cc}"
        export CC
    fi
    if [ -z "$cxx_cache_wrapper" ]; then
        CXX="$cache_cmd ${CXX:-c++}"
        export CXX
    fi
    unset cc_cache_wrapper cxx_cache_wrapper
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

. "$script_dir/scripts/whp-build/shell-functions.sh"
whp_exec_bash "$script_dir/$bash_name" "$@"
