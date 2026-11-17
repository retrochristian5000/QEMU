#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an installed Homebrew package manager without installing it.
# Package changes and network access require an explicit forwarded brew command.
set -eu

marker=whp-qemu-brew-seed-adapter
if [ "${1:-}" = --whp-brew-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

brew_resolve()
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
    case "$candidate" in
        */seeds/brew.sh|*/scripts/whp-build/seed-bin/brew) exit 1 ;;
    esac
    identity=$("$candidate" --whp-brew-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    version=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    case "$version" in Homebrew\ *) ;; *) exit 1 ;; esac
    prefix=$("$candidate" --prefix 2>/dev/null) || exit 1
    case "$prefix" in /*) ;; *) exit 1 ;; esac
    case "$prefix" in
        *'
'*) exit 1 ;;
    esac
    if [ -n "${HOMEBREW_PREFIX:-}" ] && [ "$prefix" != "$HOMEBREW_PREFIX" ]; then
        exit 1
    fi
    printf '%s\n' "$candidate"
)

brew_select()
{
    selected=
    # WHP_HOMEBREW_BREW is the existing downstream lock. An independent
    # WHP_BREW_SEED request must agree rather than silently replace it.
    for setting in WHP_BREW_SEED WHP_HOMEBREW_BREW; do
        case "$setting" in
            WHP_BREW_SEED) requested=${WHP_BREW_SEED:-} ;;
            WHP_HOMEBREW_BREW) requested=${WHP_HOMEBREW_BREW:-} ;;
        esac
        [ -n "$requested" ] || continue
        if candidate=$(brew_resolve "$requested"); then
            if [ -n "$selected" ] && [ "$selected" != "$candidate" ]; then
                printf '%s\n' 'error: WHP_BREW_SEED conflicts with WHP_HOMEBREW_BREW' >&2
                return 1
            fi
            selected=$candidate
        else
            printf 'error: %s is not a validated Homebrew executable: %s\n' \
                "$setting" "$requested" >&2
            return 1
        fi
    done
    if [ -n "$selected" ]; then
        printf '%s\n' "$selected"
        return 0
    fi

    # An explicit prefix is a constraint, not permission to switch managers.
    if [ -n "${HOMEBREW_PREFIX:-}" ]; then
        if selected=$(brew_resolve "$HOMEBREW_PREFIX/bin/brew"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: no valid Homebrew found under HOMEBREW_PREFIX=%s\n' \
            "$HOMEBREW_PREFIX" >&2
        return 1
    fi

    # Prefer the matching macOS architecture, not the opposite Rosetta prefix.
    set -- brew
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        case "$(uname -m 2>/dev/null || true)" in
            arm64|aarch64|arm64e) set -- /opt/homebrew/bin/brew brew ;;
            x86_64) set -- /usr/local/bin/brew brew ;;
        esac
    fi
    for requested do
        if selected=$(brew_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no installed Homebrew passed the brew seed probe' >&2
    return 1
}


# Read-only executable lookup for an installed formula, including keg-only
# formulae which are deliberately not linked into Homebrew's shared bin.
brew_formula_binary()
{
    if [ "$#" -ne 2 ]; then
        printf '%s\n' 'usage: brew.sh --formula-bin FORMULA EXECUTABLE' >&2
        return 2
    fi
    formula=$1
    binary=$2
    case "$formula" in
        ''|[!A-Za-z0-9]*|*[!A-Za-z0-9@+_.-]*|*..*)
            printf 'error: invalid Homebrew formula name: %s\n' "$formula" >&2
            return 2 ;;
    esac
    case "$binary" in
        ''|[!A-Za-z0-9]*|*[!A-Za-z0-9@+_.-]*|*..*)
            printf 'error: invalid Homebrew executable name: %s\n' "$binary" >&2
            return 2 ;;
    esac
    selected_brew=$(brew_select) || return 1
    selected_prefix=$("$selected_brew" --prefix) || return 1
    formula_prefix=$("$selected_brew" --prefix --installed "$formula" 2>/dev/null) || {
        printf 'error: Homebrew formula is not installed: %s\n' "$formula" >&2
        return 1
    }
    case "$formula_prefix" in
        "$selected_prefix"/opt/*|"$selected_prefix"/Cellar/*) ;;
        *)
            printf 'error: Homebrew formula %s resolved outside selected prefix: %s\n' \
                "$formula" "$formula_prefix" >&2
            return 1 ;;
    esac
    case "$formula_prefix" in
        *'
'*)
            printf 'error: Homebrew formula %s returned multiple paths\n' "$formula" >&2
            return 1 ;;
    esac
    for candidate in "$formula_prefix/bin/$binary" "$formula_prefix/sbin/$binary"; do
        if [ -f "$candidate" ] && [ -x "$candidate" ]; then
            printf '%s\n' "$candidate"
            return 0
        fi
    done
    printf 'error: %s is not an installed executable in Homebrew formula %s\n' \
        "$binary" "$formula" >&2
    return 1
}

case "${1:-}" in
    --print-seed) brew_select ;;
    --formula-bin)
        shift
        brew_formula_binary "$@" ;;
    --check)
        selected=$(brew_select) || exit 1
        prefix=$("$selected" --prefix) || exit 1
        printf 'WHP Homebrew seed: %s (prefix: %s)\n' \
            "$selected" "$prefix" ;;
    *)
        selected=$(brew_select) || exit 1
        exec "$selected" "$@" ;;
esac
