#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Minimal sed seed adapter for the WHP QEMU bootstrap graph.
#
# This file is intentionally usable before Python, Automake, GNU sed, or the
# managed Autotools stack exists. It does not emulate sed. It selects and
# sanity-checks one host sed implementation, then delegates the original
# arguments unchanged. Once the pinned GNU sed is built, QEMU exports that
# binary directly and this adapter leaves the active build path.

set -eu

WHP_SED_ADAPTER_MARKER=whp-qemu-sed-seed-adapter

if [ "${1:-}" = --whp-sed-adapter-probe ]; then
    printf '%s\n' "$WHP_SED_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-sed-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_SED_ADAPTER_MARKER" ]
}

resolve_candidate()
{
    value=$1
    [ -n "$value" ] || return 1

    if [ -x "$value" ]; then
        candidate=$value
    else
        case "$value" in
            *[[:space:]]*) return 1 ;;
        esac
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 1

    result=$(printf 'alpha\n' | "$candidate" -n 's/^alpha$/beta/p' 2>/dev/null || true)
    [ "$result" = beta ] || return 1

    printf '%s\n' "$candidate"
}

select_seed()
{
    if [ -n "${WHP_SED_SEED:-}" ]; then
        resolve_candidate "$WHP_SED_SEED" ||
            {
                printf 'error: WHP_SED_SEED is not a usable sed: %s\n'                     "$WHP_SED_SEED" >&2
                return 1
            }
        return 0
    fi

    if [ -n "${SED:-}" ]; then
        if seed=$(resolve_candidate "$SED"); then
            printf '%s\n' "$seed"
            return 0
        fi
    fi

    for candidate in gsed /usr/bin/sed /bin/sed sed; do
        if seed=$(resolve_candidate "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done

    printf '%s\n'         'error: no usable host sed is available for the QEMU bootstrap seed' >&2
    return 1
}

seed=$(select_seed)

case "${1:-}" in
    --print-seed)
        printf '%s\n' "$seed"
        exit 0
        ;;
    --check)
        printf 'WHP sed seed: %s\n' "$seed"
        exit 0
        ;;
esac

exec "$seed" "$@"
