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

case "${1:-}" in
    --print-seed) brew_select ;;
    --check)
        selected=$(brew_select) || exit 1
        prefix=$("$selected" --prefix) || exit 1
        printf 'WHP Homebrew seed: %s (prefix: %s)\n' \
            "$selected" "$prefix" ;;
    *)
        selected=$(brew_select) || exit 1
        exec "$selected" "$@" ;;
esac
