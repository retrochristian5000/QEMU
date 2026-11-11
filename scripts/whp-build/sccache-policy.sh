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
    if [ -z "${SCCACHE_IDLE_TIMEOUT+x}" ] && [ -z "${SCCACHE_CONF:-}" ]; then
        # sccache defaults to 600 s. Release the idle daemon sooner after
        # short QEMU/LLVM jobs without restarting it between nearby compiles.
        SCCACHE_IDLE_TIMEOUT=180
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

    # Leave SCCACHE_CACHE_SIZE, SCCACHE_CLIENT_SIDE, SCCACHE_CONF and remote
    # cache configuration under user control. Never stop the shared daemon.
    return 0
}
