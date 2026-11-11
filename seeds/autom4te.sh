#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an installed GNU Autoconf/autom4te pair for native maintainer tools.
# This adapter never builds Autoconf or consumes a pending managed bootstrap.
set -eu

marker=whp-qemu-autom4te-seed-adapter
if [ "${1:-}" = --whp-autom4te-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_seed()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        *[[:space:]]*) exit 1 ;;
        */*) path=$value ;;
        *) path=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$path" ] && [ -x "$path" ] || exit 1
    case "$path" in
        /*) ;;
        */*) path=$(CDPATH= cd -P -- "${path%/*}" && pwd -P)/${path##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$path" --whp-autom4te-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    printf '%s\n' "$path"
)

gnu_autoconf_version()
(
    LC_ALL=C
    export LC_ALL
    banner=$("$1" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'(GNU Autoconf)'*) ;;
        *) exit 1 ;;
    esac
    version=${first##* }
    case "$version" in
        [0-9]*.[0-9]*) ;;
        *) exit 1 ;;
    esac
    case "$version" in
        *[!0-9.]*|*..*|*.) exit 1 ;;
    esac
    printf '%s\n' "$version"
)

select_pair()
(
    requested_autom4te=${WHP_AUTOM4TE_SEED:-${AUTOM4TE:-}}
    requested_autoconf=${WHP_AUTOCONF_SEED:-${AUTOCONF:-}}
    if [ -n "$requested_autom4te" ]; then
        autom4te=$(resolve_seed "$requested_autom4te") || {
            printf 'error: invalid explicit autom4te seed: %s\n' "$requested_autom4te" >&2
            exit 1
        }
    elif [ -n "$requested_autoconf" ]; then
        autoconf=$(resolve_seed "$requested_autoconf") || {
            printf 'error: invalid explicit Autoconf seed: %s\n' "$requested_autoconf" >&2
            exit 1
        }
        autom4te=$(resolve_seed "${autoconf%/*}/autom4te") || {
            printf 'error: no autom4te alongside selected Autoconf: %s\n' "$autoconf" >&2
            exit 1
        }
    else
        autom4te=$(resolve_seed autom4te) || {
            printf '%s\n' 'error: no usable autom4te seed on PATH' >&2
            exit 1
        }
    fi

    if [ -n "$requested_autoconf" ]; then
        autoconf=$(resolve_seed "$requested_autoconf") || {
            printf 'error: invalid explicit Autoconf seed: %s\n' "$requested_autoconf" >&2
            exit 1
        }
    elif [ -x "${autom4te%/*}/autoconf" ]; then
        autoconf=$(resolve_seed "${autom4te%/*}/autoconf") || exit 1
    else
        autoconf=$(resolve_seed autoconf) || {
            printf '%s\n' 'error: no usable Autoconf seed on PATH' >&2
            exit 1
        }
    fi
    av=$(gnu_autoconf_version "$autom4te") || {
        printf 'error: autom4te is not GNU Autoconf: %s\n' "$autom4te" >&2
        exit 1
    }
    cv=$(gnu_autoconf_version "$autoconf") || {
        printf 'error: autoconf is not GNU Autoconf: %s\n' "$autoconf" >&2
        exit 1
    }
    [ "$av" = "$cv" ] || {
        printf 'error: Autoconf/autom4te release mismatch: %s != %s\n' "$cv" "$av" >&2
        exit 1
    }
    printf '%s\n%s\n' "$autom4te" "$autoconf"
)

pair=$(select_pair) || exit 1
autom4te=${pair%%'
'*}
autoconf=${pair#*'
'}
case "${1:-}" in
    --print-seed|--print-autom4te) printf '%s\n' "$autom4te" ;;
    --print-autoconf) printf '%s\n' "$autoconf" ;;
    --check)
        printf 'WHP GNU autom4te seed: %s\nWHP GNU Autoconf seed: %s\n' "$autom4te" "$autoconf" ;;
    --autoconf)
        shift
        exec "$autoconf" "$@" ;;
    *)
        exec "$autom4te" "$@" ;;
esac
