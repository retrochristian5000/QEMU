#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an existing native Perl for the pre-Autotools bootstrap.
# Perl is a root dependency, not a tool that this adapter builds.
set -eu

marker=whp-qemu-perl-seed-adapter
if [ "${1:-}" = --whp-perl-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

perl_resolve()
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
    identity=$("$candidate" --whp-perl-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1

    # Version and execution, not a plausible --version banner: the Automake
    # maintainer tree requires Perl >= 5.6 and uses core strict/warnings.
    result=$("$candidate" -e 'use 5.006; use strict; use warnings; print "whp-perl-ok\n";' 2>/dev/null) || exit 1
    [ "$result" = whp-perl-ok ] || exit 1

    printf '%s\n' "$candidate"
)

perl_select()
{
    # An explicit choice is authoritative. Do not fall back to PATH when it
    # is absent, malformed, too old, or is this adapter.
    for variable in WHP_PERL_SEED PERL; do
        case "$variable" in
            WHP_PERL_SEED) requested=${WHP_PERL_SEED:-} ;;
            PERL) requested=${PERL:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(perl_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not select usable Perl >= 5.6: %s\n' "$variable" "$requested" >&2
        return 1
    done

    for candidate in perl /usr/bin/perl; do
        if selected=$(perl_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable native Perl >= 5.6 for Autotools bootstrap' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-perl) perl_select ;;
    --check)
        selected=$(perl_select) || exit 1
        printf 'WHP Perl seed: %s\n' "$selected" ;;
    *)
        selected=$(perl_select) || exit 1
        exec "$selected" "$@" ;;
esac
