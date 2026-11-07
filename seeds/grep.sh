#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Seed-only grep bridge. Do not introduce a grep -> GNU grep build cycle.
set -eu

WHP_GREP_ADAPTER_MARKER=whp-qemu-grep-seed-adapter
if [ "${1:-}" = --whp-grep-adapter-probe ]; then
    printf '%s\n' "$WHP_GREP_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    marker=$("$1" --whp-grep-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_GREP_ADAPTER_MARKER" ]
}

semantic_probe()
(
    candidate=$1
    LC_ALL=C
    export LC_ALL

    result=$(printf 'alpha\nbeta\n' | "$candidate" -F -x beta 2>/dev/null) || exit 1
    [ "$result" = beta ] || exit 1

    result=$(printf 'a+b\n' | "$candidate" -E '^a\+b$' 2>/dev/null) || exit 1
    [ "$result" = 'a+b' ] || exit 1

    printf 'Alpha\n' | "$candidate" -i -q '^alpha$' 2>/dev/null || exit 1

    result=$(printf 'alpha\nbeta\n' | "$candidate" -v '^beta$' 2>/dev/null) || exit 1
    [ "$result" = alpha ] || exit 1

    result=$(printf '%s\n' '-literal' | "$candidate" -F -e '-literal' 2>/dev/null) || exit 1
    [ "$result" = '-literal' ] || exit 1
)

resolve_candidate()
(
    value=$1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null || true) ;;
    esac
    [ -n "$candidate" ] && [ -x "$candidate" ] || exit 1

    case "$candidate" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/}
            ;;
        *) exit 1 ;;
    esac

    is_self "$candidate" && exit 3
    semantic_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

select_seed()
{
    for name in WHP_GREP_SEED GREP; do
        case "$name" in
            WHP_GREP_SEED) requested=${WHP_GREP_SEED:-} ;;
            GREP) requested=${GREP:-} ;;
        esac
        [ -n "$requested" ] || continue
        if seed=$(resolve_candidate "$requested"); then
            printf '%s\n' "$seed"
            return 0
        else
            code=$?
        fi
        if [ "$code" -eq 3 ]; then
            printf 'error: %s points back to the QEMU grep adapter\n' "$name" >&2
        else
            printf 'error: %s is not a usable grep: %s\n' "$name" "$requested" >&2
        fi
        return 1
    done

    for candidate in ggrep /usr/bin/grep /bin/grep grep; do
        if seed=$(resolve_candidate "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable host grep supports the WHP bootstrap semantics' >&2
    return 1
}

case "${1:-}" in
    --print-seed)
        select_seed
        exit $? ;;
    --check)
        seed=$(select_seed) || exit 1
        printf 'WHP grep seed: %s\n' "$seed"
        exit 0 ;;
esac

# The public build validates once, then all literal grep calls use its locked
# executable without repeating semantic probes on the bootstrap hot path.
if [ "${WHP_GREP_LOCKED:-0}" = 1 ] && [ -n "${WHP_GREP_SEED:-}" ]; then
    case "$WHP_GREP_SEED" in
        */grep.sh|*/scripts/whp-build/seed-bin/grep)
            printf '%s\n' 'error: locked GREP points to the grep bridge' >&2
            exit 1 ;;
    esac
    [ -x "$WHP_GREP_SEED" ] || {
        printf 'error: locked GREP is not executable: %s\n' "$WHP_GREP_SEED" >&2
        exit 1
    }
    exec "$WHP_GREP_SEED" "$@"
fi

seed=$(select_seed) || exit 1
exec "$seed" "$@"
