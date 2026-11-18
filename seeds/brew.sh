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

# Deliberate, read-only inventory; QEMU seed adapters remain the authority for
# capabilities. A PATH command is not automatically an acceptable GNU tool.
brew_audit_one()
(
    selected_brew=$1
    selected_prefix=$2
    label=$3
    formula=$4
    binary=$5
    native=$6
    brew_status=unavailable
    if [ -n "$selected_brew" ]; then
        if formula_prefix=$("$selected_brew" --prefix --installed "$formula" 2>/dev/null); then
            case "$formula_prefix" in
                "$selected_prefix"/opt/*|"$selected_prefix"/Cellar/*)
                    brew_status=incomplete
                    for candidate in "$formula_prefix/bin/$binary" "$formula_prefix/sbin/$binary"; do
                        if [ -f "$candidate" ] && [ -x "$candidate" ]; then
                            brew_status=installed:"$candidate"
                            break
                        fi
                    done ;;
                *) brew_status=incomplete ;;
            esac
        else
            brew_status=missing
        fi
    fi
    native_status=absent
    if native_path=$(command -v "$native" 2>/dev/null); then
        native_status=unverified:"$native_path"
    fi
    printf '%s: formula=%s executable=%s homebrew=%s native=%s\n' \
        "$label" "$formula" "$binary" "$brew_status" "$native_status"
)

brew_audit_tools()
{
    if [ "$#" -ne 0 ]; then
        printf '%s\n' 'usage: brew.sh --audit-tools' >&2
        return 2
    fi
    selected_brew=
    selected_prefix=
    provider=${WHP_MACOS_DEPENDENCY_PROVIDER:-auto}
    case "$provider" in
        macports|system)
            printf 'WHP Homebrew audit: provider=%s (not selected)\n' "$provider" ;;
        auto|homebrew)
            if selected_brew=$(brew_select 2>/dev/null); then
                selected_prefix=$("$selected_brew" --prefix) || return 1
                printf 'WHP Homebrew audit: manager=%s prefix=%s\n' \
                    "$selected_brew" "$selected_prefix"
            else
                # A broken explicit lock is an error, not optional absence.
                if [ "$provider" = homebrew ] ||
                   [ -n "${WHP_BREW_SEED:-}${WHP_HOMEBREW_BREW:-}${HOMEBREW_PREFIX:-}" ]; then
                    brew_select >/dev/null
                    return 1
                fi
                printf '%s\n' 'WHP Homebrew audit: manager=unavailable (native tools may still work)'
            fi ;;
        *)
            printf 'error: invalid macOS dependency provider: %s\n' "$provider" >&2
            return 2 ;;
    esac
    printf '%s\n' 'WHP Homebrew audit: inventory only; native PATH candidates are not capability-tested'
    # These roles are feature-conditional. Absence is advisory, not fatal.
    brew_audit_one "$selected_brew" "$selected_prefix" gnu-m4 m4 m4 m4
    brew_audit_one "$selected_brew" "$selected_prefix" bison bison bison bison
    brew_audit_one "$selected_brew" "$selected_prefix" texinfo texinfo makeinfo makeinfo
    brew_audit_one "$selected_brew" "$selected_prefix" gnu-sed gnu-sed gsed sed
    brew_audit_one "$selected_brew" "$selected_prefix" gnu-install coreutils ginstall install
    brew_audit_one "$selected_brew" "$selected_prefix" pkg-config pkgconf pkg-config pkg-config
    brew_audit_one "$selected_brew" "$selected_prefix" autoconf autoconf autoconf autoconf
    brew_audit_one "$selected_brew" "$selected_prefix" automake automake automake automake
    brew_audit_one "$selected_brew" "$selected_prefix" gawk gawk gawk awk
    brew_audit_one "$selected_brew" "$selected_prefix" cmake cmake cmake cmake
    brew_audit_one "$selected_brew" "$selected_prefix" ninja ninja ninja ninja
}

case "${1:-}" in
    --print-seed) brew_select ;;
    --formula-bin)
        shift
        brew_formula_binary "$@" ;;
    --audit-tools)
        shift
        brew_audit_tools "$@" ;;
    --check)
        selected=$(brew_select) || exit 1
        prefix=$("$selected" --prefix) || exit 1
        printf 'WHP Homebrew seed: %s (prefix: %s)\n' \
            "$selected" "$prefix" ;;
    *)
        selected=$(brew_select) || exit 1
        exec "$selected" "$@" ;;
esac
