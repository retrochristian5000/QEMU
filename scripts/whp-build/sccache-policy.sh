#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Source from the host QEMU and native LLVM build wrappers, only for sccache.
# Keep this independent of the installed QEMU and LLVM toolchain ABI.
#
# SCCACHE_IDLE_TIMEOUT controls how long the sccache daemon may remain idle,
# NOT the amount of RAM available to the compiler. Do not set
# SCCACHE_CLIENT_SIDE automatically: it needs a recent sccache release and
# separate cache-hit validation. SCCACHE_CACHE_SIZE controls disk, not RAM.

whp_sccache_memory_policy()
{
    case "${WHP_SCCACHE_PROFILE-conservative}" in
        conservative|performance) ;;
        *)
            printf 'error: WHP_SCCACHE_PROFILE must be conservative or performance\n' >&2
            return 1
            ;;
    esac

    if [ -z "${SCCACHE_CONF:-}" ]; then
        if [ -z "${SCCACHE_IDLE_TIMEOUT+x}" ]; then
            case "${WHP_SCCACHE_PROFILE-conservative}" in
                conservative) SCCACHE_IDLE_TIMEOUT=180 ;;
                performance) SCCACHE_IDLE_TIMEOUT=600 ;;
            esac
        fi
        if [ "${WHP_SCCACHE_PROFILE-conservative}" = performance ] &&
           [ -z "${SCCACHE_CACHE_ZSTD_LEVEL+x}" ]; then
            SCCACHE_CACHE_ZSTD_LEVEL=1
            export SCCACHE_CACHE_ZSTD_LEVEL
        fi
    fi

    if [ -n "${SCCACHE_IDLE_TIMEOUT+x}" ]; then
        case "$SCCACHE_IDLE_TIMEOUT" in
            ''|*[!0-9]*)
                printf 'error: SCCACHE_IDLE_TIMEOUT must be seconds (0 means never): %s\n' \
                    "$SCCACHE_IDLE_TIMEOUT" >&2
                return 1
                ;;
        esac
        export SCCACHE_IDLE_TIMEOUT
    fi

    # Leave cache capacity, direct mode, client-side mode and remote storage
    # under user control. Never stop the shared daemon.
    return 0
}
