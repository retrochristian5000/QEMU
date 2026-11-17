#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Generic M4 seed: portable macros only; GNU-only consumers use gnum4.sh.
set -eu

marker=whp-qemu-m4-seed-adapter
if [ "${1:-}" = --whp-m4-adapter-probe ] ||
   [ "${1:-}" = --whp-gnum4-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

m4_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-m4-adapter-probe 2>/dev/null || true)
    case "$identity" in
        whp-qemu-m4-seed-adapter|whp-qemu-gnum4-seed-adapter) exit 1 ;;
    esac
    # No --gnu assumption: these are traditional portable M4 builtins.
    result=$(printf '%s\n' \
        'changequote([,])dnl' \
        'define([WHP_M4_SEED_PROBE],[ready])dnl' \
        'WHP_M4_SEED_PROBE' |
        "$candidate" 2>/dev/null) || exit 1
    [ "$result" = ready ] || exit 1
    printf '%s\n' "$candidate"
)

m4_select()
{
    for variable in WHP_M4_SEED M4; do
        case "$variable" in
            WHP_M4_SEED) requested=${WHP_M4_SEED:-} ;;
            M4) requested=${M4:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(m4_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not select a working generic M4: %s\n' \
            "$variable" "$requested" >&2
        return 1
    done
    for candidate in m4 gm4 gnum4; do
        if selected=$(m4_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no working generic M4 is available' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-m4) m4_select ;;
    --check)
        selected=$(m4_select) || exit 1
        printf 'WHP generic M4 seed: %s\n' "$selected" ;;
    *)
        selected=$(m4_select) || exit 1
        exec "$selected" "$@" ;;
esac
