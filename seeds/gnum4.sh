#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Dedicated GNU M4 seed for maintainer-source Autotools generation.
set -eu

marker=whp-qemu-gnum4-seed-adapter
if [ "${1:-}" = --whp-m4-adapter-probe ] || [ "${1:-}" = --whp-gnum4-adapter-probe ]; then
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
    banner=$("$candidate" --gnu --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'GNU M4'*) ;;
        *) exit 1 ;;
    esac
    version=${first##* }
    major=${version%%.*}
    remainder=${version#*.}
    [ "$remainder" != "$version" ] || exit 1
    minor=${remainder%%.*}
    patch=0
    case "$remainder" in
        *.*) patch=${remainder#*.}; patch=${patch%%[!0-9]*} ;;
    esac
    case "$major:$minor:$patch" in
        *[!0-9:]*|:*|*::*) exit 1 ;;
    esac
    [ -n "$major" ] && [ -n "$minor" ] || exit 1
    if [ "$major" -eq 1 ]; then
        if [ "$minor" -lt 4 ]; then exit 1; fi
        if [ "$minor" -eq 4 ] && [ "$patch" -lt 16 ]; then exit 1; fi
    elif [ "$major" -lt 1 ]; then
        exit 1
    fi
    result=$(printf '%s\n' "patsubst(\`ab12cd', \`[0-9]+', \`X')" |
        "$candidate" --gnu --fatal-warnings 2>/dev/null) || exit 1
    [ "$result" = abXcd ] || exit 1

    # Autoconf's m4/m4.m4 uses both trace output and frozen-state files.
    # A working patsubst and a GNU version banner do not prove either.
    trace=$(printf '%s\n' \
        'changequote(<,>)define(<T>,<>)dnl' \
        'define(<F>,<T(<traced>)>)dnl' \
        'm4wrap(<F>)dnl' |
        "$candidate" --gnu --trace=T --debug=aflq 2>&1) || {
        printf 'error: GNU M4 Autoconf trace probe failed: %s\n' "$candidate" >&2
        exit 1
    }
    [ "$trace" = 'm4trace:stdin:3: -1- T(<traced>)' ] || {
        printf 'error: GNU M4 Autoconf trace output is incompatible: %s; got %s\n' \
            "$candidate" "$trace" >&2
        exit 1
    }
    "$candidate" --gnu -F /dev/null </dev/null >/dev/null 2>&1 || {
        printf 'error: GNU M4 Autoconf frozen-state probe failed: %s\n' "$candidate" >&2
        exit 1
    }
    printf '%s\n' "$candidate"
)

m4_select()
{
    # Explicit values are authoritative and must never fall through to PATH.
    for variable in WHP_GNUM4_SEED GNUM4 WHP_M4_SEED M4; do
        case "$variable" in
            WHP_GNUM4_SEED) requested=${WHP_GNUM4_SEED:-} ;;
            GNUM4) requested=${GNUM4:-} ;;
            WHP_M4_SEED) requested=${WHP_M4_SEED:-} ;;
            M4) requested=${M4:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(m4_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s does not select GNU M4 >= 1.4.16 with working macros, traces, and freeze-state: %s\n' "$variable" "$requested" >&2
        return 1
    done

    # macOS Homebrew M4 can be keg-only. Ask the selected Brew installation
    # for the installed formula's executable; never guess another prefix.
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        case "${WHP_MACOS_DEPENDENCY_PROVIDER:-auto}" in
            macports|system) ;;
            *)
                seed_dir=$(CDPATH= cd -P -- "$(dirname -- "$0")" && pwd -P) || return 1
                if candidate=$(/bin/sh "$seed_dir/brew.sh" --formula-bin m4 m4 2>/dev/null); then
                    if selected=$(m4_resolve "$candidate"); then
                        printf '%s\n' "$selected"
                        return 0
                    fi
                fi
                ;;
        esac
    fi

    for candidate in m4 gm4 gnum4; do
        if selected=$(m4_resolve "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: GNU M4 >= 1.4.16 with working macros, traces, and frozen-state support is required' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-m4|--print-gnum4) m4_select ;;
    --check)
        selected=$(m4_select) || exit 1
        printf 'WHP GNU M4 seed: %s\n' "$selected" ;;
    *)
        selected=$(m4_select) || exit 1
        exec "$selected" "$@" ;;
esac
