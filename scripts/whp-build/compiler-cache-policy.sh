#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional local compiler cache disk budget, not a compiler memory limit.
# Provider-specific environment and explicitly selected config files win.
whp_compiler_cache_budget()
{
    case "$1" in
        ccache|sccache) ;;
        *) printf 'error: unsupported compiler cache provider: %s\n' "$1" >&2
           return 1 ;;
    esac
    budget=${WHP_COMPILER_CACHE_SIZE:-}
    [ -n "$budget" ] || return 0
    # Bound the input to a positive integer followed by M or G. Do not
    # accept zero (which can mean unlimited) or unbounded integer strings.
    case "$budget" in
        *M|*G) magnitude=${budget%?} ;;
        *) magnitude= ;;
    esac
    case "$magnitude" in
        ''|0*|*[!0-9]*|?????????*)
            printf '%s\n' 'error: WHP_COMPILER_CACHE_SIZE must be a positive integer (up to eight digits) followed by M or G' >&2
            return 1 ;;
    esac
    case "$1" in
        ccache)
            if [ -z "${CCACHE_CONFIGPATH:-}" ] && [ -z "${CCACHE_MAXSIZE+x}" ]; then
                CCACHE_MAXSIZE=$budget
                export CCACHE_MAXSIZE
            fi ;;
        sccache)
            if [ -z "${SCCACHE_CONF:-}" ] && [ -z "${SCCACHE_CACHE_SIZE+x}" ]; then
                SCCACHE_CACHE_SIZE=$budget
                export SCCACHE_CACHE_SIZE
            fi ;;
    esac
    unset budget magnitude
}
