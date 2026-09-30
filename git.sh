#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Seed Git adapter for the WHP QEMU bootstrap graph.
#
# Git cannot bootstrap the checkout that contains its own pinned source.
# An already usable host Git is therefore an explicit root capability.

set -eu

WHP_GIT_ADAPTER_MARKER=whp-qemu-git-seed-adapter

if [ "${1:-}" = --whp-git-adapter-probe ]; then
    printf '%s\n' "$WHP_GIT_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-git-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_GIT_ADAPTER_MARKER" ]
}

resolve_candidate()
{
    value=$1
    [ -n "$value" ] || return 1
    case "$value" in
        *[[:space:]]*) return 1 ;;
    esac
    if [ -x "$value" ]; then
        candidate=$value
    else
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 1
    "$candidate" --version 2>/dev/null | grep -q '^git version ' || return 1
    printf '%s\n' "$candidate"
}

select_seed()
{
    if [ -n "${WHP_GIT_SEED:-}" ]; then
        resolve_candidate "$WHP_GIT_SEED" ||
            {
                printf 'error: WHP_GIT_SEED is not a usable Git: %s\n' \
                    "$WHP_GIT_SEED" >&2
                return 1
            }
        return 0
    fi

    for candidate in /usr/bin/git /opt/homebrew/bin/git /usr/local/bin/git git; do
        if seed=$(resolve_candidate "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' \
        'error: no usable host Git is available for the QEMU bootstrap seed' >&2
    return 1
}

seed=$(select_seed)

case "${1:-}" in
    --print-seed)
        printf '%s\n' "$seed"
        exit 0
        ;;
    --check)
        printf 'WHP Git seed: %s\n' "$seed"
        exit 0
        ;;
esac

exec "$seed" "$@"
