#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# BusyBox [ applet seed, independent of the generic external [ and shell test.
# Selection is optional: no BusyBox installation or bootstrap is performed.
set -eu

marker=whp-qemu-bb-bracket-seed-adapter
if [ "${1:-}" = --whp-bb-bracket-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

bb_bracket_syntax_error()
(
    provider=$1
    shift
    if "$provider" '[' "$@" 2>/dev/null; then
        exit 1
    else
        status=$?
        [ "$status" -gt 1 ]
    fi
)

bb_bracket_probe()
(
    provider=$1
    # Invoke BusyBox's applet explicitly. A bare '[' may be a shell builtin.
    "$provider" '[' -n value ']' || exit 1
    if "$provider" '[' -n '' ']'; then exit 1; fi
    "$provider" '[' value = value ']' || exit 1
    if "$provider" '[' value != value ']'; then exit 1; fi
    "$provider" '[' -f "$provider" ']' || exit 1
    "$provider" '[' -x "$provider" ']' || exit 1
    "$provider" '[' ! -n '' ']' || exit 1
    "$provider" '[' ']' = ']' ']' || exit 1

    # Missing/malformed final ] is a syntax error, not a false condition.
    bb_bracket_syntax_error "$provider" -n value || exit 1
    bb_bracket_syntax_error "$provider" -n value not-a-bracket || exit 1
    bb_bracket_syntax_error "$provider" -n value '' || exit 1
)

bb_bracket_resolve()
(
    requested=$1
    [ -n "$requested" ] || exit 1
    case "$requested" in
        */*) provider=$requested ;;
        *[[:space:]]*) exit 1 ;;
        *) provider=$(command -v "$requested" 2>/dev/null) || exit 1 ;;
    esac
    # A shell builtin, an adapter, or an inaccessible file is not BusyBox.
    [ -f "$provider" ] && [ -x "$provider" ] || exit 1
    case "$provider" in
        /*) ;;
        */*)
            directory=$(CDPATH= cd -P -- "${provider%/*}" && pwd -P) || exit 1
            provider=$directory/${provider##*/}
            ;;
        *) exit 1 ;;
    esac

    identity=$("$provider" --whp-bb-bracket-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    identity=$("$provider" --whp-bracket-adapter-probe 2>/dev/null || true)
    [ "$identity" != whp-qemu-bracket-seed-adapter ] || exit 1

    # Require BusyBox multicall identity AND an advertised '[' applet.
    # The functional probe below rejects version-banner-only impostors.
    banner=$(LC_ALL=C "$provider" --help 2>&1) || exit 1
    case "$banner" in
        'BusyBox v'*'multi-call binary.'*) ;;
        *) exit 1 ;;
    esac
    applets=$(LC_ALL=C "$provider" --list 2>/dev/null) || exit 1
    case "
$applets
" in
        *'
[
'*) ;;
        *) exit 1 ;;
    esac
    bb_bracket_probe "$provider" || exit 1
    printf '%s\n' "$provider"
)

bb_bracket_select()
{
    # Never inherit WHP_BRACKET_SEED: this provider must be BusyBox itself.
    if [ -n "${WHP_BB_BRACKET_SEED:-}" ]; then
        bb_bracket_resolve "$WHP_BB_BRACKET_SEED" || {
            printf 'error: invalid BusyBox [ seed in WHP_BB_BRACKET_SEED: %s\n' \
                "$WHP_BB_BRACKET_SEED" >&2
            return 1
        }
        return 0
    fi
    for candidate in busybox /usr/bin/busybox /bin/busybox; do
        if bb_bracket_resolve "$candidate"; then
            return 0
        fi
    done
    printf '%s\n' 'error: BusyBox [ applet is unavailable; generic [ is not a fallback' >&2
    return 1
}

case "${1:-}" in
    --print-seed)
        # Return the BusyBox multicall executable (not a generic [ path).
        bb_bracket_select ;;
    --check)
        selected=$(bb_bracket_select) || exit 1
        printf 'WHP BusyBox [ seed: %s\n' "$selected"
        # -ef is diagnostic, not mandatory on older BusyBox releases.
        if "$selected" '[' "$selected" -ef "$selected" ']' 2>/dev/null; then
            printf '%s\n' 'WHP BusyBox [ -ef: supported'
        else
            printf '%s\n' 'WHP BusyBox [ -ef: unavailable'
        fi
        ;;
    *)
        selected=$(bb_bracket_select) || exit 1
        exec "$selected" '[' "$@"
        ;;
esac
