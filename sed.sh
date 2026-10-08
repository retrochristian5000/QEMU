#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Pre-GNU-sed adapter for the WHP QEMU bootstrap graph.
#
# GNU sed's Git bootstrap itself requires sed. This adapter therefore has one
# deliberately small job: resolve a real host sed, verify the subset QEMU's
# bootstrap needs, reject recursion, and delegate arguments unchanged. Once
# the pinned GNU sed is installed, the build exports that binary directly and
# this adapter leaves the active path.

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

semantic_probe()
{
    candidate=$1

    result=$(printf 'alpha\n' | "$candidate" -n 's/^alpha$/beta/p' 2>/dev/null || true)
    [ "$result" = beta ] || return 1

    result=$(printf 'A B/C\n' | "$candidate" 's,[^A-Za-z0-9_.-],-,g' 2>/dev/null || true)
    [ "$result" = A-B-C ] || return 1

    result=$(printf 'AR=/tmp/llvm-ar|LLVM\n' | \
        "$candidate" -n 's#^AR=\([^|]*\)|.*$#\1#p' 2>/dev/null || true)
    [ "$result" = /tmp/llvm-ar ] || return 1

    result=$(printf 'one\ntwo\n' | "$candidate" -n '1p' 2>/dev/null || true)
    [ "$result" = one ] || return 1
}

resolve_candidate()
{
    value=$1
    [ -n "$value" ] || return 1

    case "$value" in
        */*)
            candidate=$value
            [ -x "$candidate" ] || return 1
            ;;
        *[[:space:]]*)
            return 1
            ;;
        *)
            candidate=$(command -v "$value" 2>/dev/null || true)
            [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
            ;;
    esac

    is_self "$candidate" && return 3
    semantic_probe "$candidate" || return 1
    printf '%s\n' "$candidate"
}

select_seed()
{
    if [ -n "${WHP_SED_SEED:-}" ]; then
        if seed=$(resolve_candidate "$WHP_SED_SEED"); then
            printf '%s\n' "$seed"
            return 0
        else
            rc=$?
        fi
        if [ "$rc" -eq 3 ]; then
            printf '%s\n' \
                'error: WHP_SED_SEED points back to the QEMU sed adapter' >&2
        else
            printf 'error: WHP_SED_SEED is not a usable sed: %s\n' \
                "$WHP_SED_SEED" >&2
        fi
        return 1
    fi

    if [ -n "${SED:-}" ]; then
        if seed=$(resolve_candidate "$SED"); then
            printf '%s\n' "$seed"
            return 0
        fi
    fi

    for value in gsed /usr/bin/sed /bin/sed sed; do
        if seed=$(resolve_candidate "$value"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done

    printf '%s\n' \
        'error: no usable host sed is available for the QEMU bootstrap seed' >&2
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

# Keep the normal hot path as an exec.  Only opt-in failure tracing keeps
# the adapter alive to report the actual argv handed to the seed sed.  This
# catches malformed generated substitutions without changing their semantics.
if [ "${WHP_SED_TRACE:-0}" = errors ]; then
    if "$seed" "$@"; then
        exit 0
    else
        rc=$?
        printf 'WHP sed seed failed (exit %s): %s\n' "$rc" "$seed" >&2
        index=0
        for arg do
            printf '  argv[%s]=<%s>\n' "$index" "$arg" >&2
            index=$((index + 1))
        done
        exit "$rc"
    fi
fi

exec "$seed" "$@"
