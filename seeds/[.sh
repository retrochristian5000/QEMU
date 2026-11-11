#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Diagnose/select the external POSIX [ utility without replacing shell builtins.
# Use --check for a bounded pre-bootstrap diagnostic, not on every predicate.
set -eu

marker=whp-qemu-bracket-seed-adapter
if [ "${1:-}" = --whp-bracket-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

bracket_probe()
(
    candidate=$1
    # The external utility requires a separate closing ] argument.
    "$candidate" -n value ] || exit 1
    if "$candidate" -n '' ]; then exit 1; fi
    "$candidate" value = value ] || exit 1
    if "$candidate" value != value ]; then exit 1; fi
    "$candidate" -f "$candidate" ] || exit 1
    "$candidate" -x "$candidate" ] || exit 1
    "$candidate" ! -n '' ] || exit 1
)

bracket_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    # Do not mistake the shell's built-in [ for an external executable.
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
             candidate=$directory/${candidate##*/} ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-bracket-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    bracket_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

bracket_select()
{
    if [ -n "${WHP_BRACKET_SEED:-}" ]; then
        bracket_resolve "$WHP_BRACKET_SEED" || {
            printf 'error: WHP_BRACKET_SEED is not a usable external [: %s\n' "$WHP_BRACKET_SEED" >&2
            return 1
        }
        return 0
    fi
    for candidate in /usr/bin/'[' /bin/'['; do
        if bracket_resolve "$candidate"; then
            return 0
        fi
    done
    printf '%s\n' 'error: no standalone external [ utility passed the seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed) bracket_select ;;
    --check)
        selected=$(bracket_select) || exit 1
        printf 'WHP external bracket seed: %s\n' "$selected"
        # Report optional non-POSIX extensions separately, never require them.
        if "$selected" "$selected" -ef "$selected" ] 2>/dev/null; then
            printf '%s\n' 'WHP external bracket -ef extension: supported'
        else
            printf '%s\n' 'WHP external bracket -ef extension: unavailable'
        fi
        ;;
    *)
        selected=$(bracket_select) || exit 1
        exec "$selected" "$@"
        ;;
esac
