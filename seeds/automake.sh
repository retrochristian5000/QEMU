#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an existing GNU Automake/aclocal pair for native source generation.
# This seed does not bootstrap Automake or change the Autoconf cycle boundary.
set -eu

marker=whp-qemu-automake-seed-adapter
if [ "${1:-}" = --whp-automake-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

seed_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        *[[:space:]]*) exit 1 ;;
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    probe=$("$candidate" --whp-automake-adapter-probe 2>/dev/null || true)
    [ "$probe" != "$marker" ] || exit 1
    printf '%s\n' "$candidate"
)

seed_version()
(
    candidate=$1
    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'(GNU automake)'*) ;;
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

seed_pair()
(
    explicit_automake=${WHP_AUTOMAKE_SEED:-${AUTOMAKE:-}}
    explicit_aclocal=${WHP_ACLOCAL_SEED:-${ACLOCAL:-}}
    if [ -n "$explicit_automake" ]; then
        automake=$(seed_resolve "$explicit_automake") || {
            printf 'error: invalid explicit GNU Automake seed: %s\n' "$explicit_automake" >&2
            exit 1
        }
    else
        automake=$(seed_resolve automake) || {
            printf '%s\n' 'error: no usable GNU Automake seed on PATH' >&2
            exit 1
        }
    fi

    # Prefer the executable installed alongside the selected Automake. This
    # avoids pairing a Homebrew/managed Automake with a different PATH aclocal.
    if [ -n "$explicit_aclocal" ]; then
        aclocal=$(seed_resolve "$explicit_aclocal") || {
            printf 'error: invalid explicit aclocal seed: %s\n' "$explicit_aclocal" >&2
            exit 1
        }
    elif [ -x "${automake%/*}/aclocal" ]; then
        aclocal=$(seed_resolve "${automake%/*}/aclocal") || exit 1
    else
        aclocal=$(seed_resolve aclocal) || {
            printf '%s\n' 'error: no usable aclocal seed on PATH' >&2
            exit 1
        }
    fi

    av=$(seed_version "$automake") || {
        printf 'error: GNU Automake version is not usable: %s\n' "$automake" >&2
        exit 1
    }
    lv=$(seed_version "$aclocal") || {
        printf 'error: GNU aclocal version is not usable: %s\n' "$aclocal" >&2
        exit 1
    }
    [ "$av" = "$lv" ] || {
        printf 'error: Automake/aclocal version mismatch: %s != %s\n' "$av" "$lv" >&2
        exit 1
    }
    printf '%s\n%s\n' "$automake" "$aclocal"
)

pair=$(seed_pair) || exit 1
automake=${pair%%'
'*}
aclocal=${pair#*'
'}
case "${1:-}" in
    --print-seed|--print-automake) printf '%s\n' "$automake" ;;
    --print-aclocal) printf '%s\n' "$aclocal" ;;
    --check)
        printf 'WHP GNU Automake seed: %s\nWHP GNU aclocal seed: %s\n' "$automake" "$aclocal" ;;
    --aclocal)
        shift
        exec "$aclocal" "$@" ;;
    *)
        exec "$automake" "$@" ;;
esac
