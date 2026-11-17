#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional GNU sed selector. Native sed.sh remains the bootstrap seed.
# This script neither installs formulae nor modifies PATH.
set -eu

marker=whp-qemu-gnu-sed-seed-adapter
case "${1:-}" in
    --whp-gnu-sed-adapter-probe|--whp-sed-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

# Resolve sibling adapters through symlinked seed-bin launchers.
entry=$0
case "$entry" in
    */*) ;;
    *) entry=$(command -v "$entry") || exit 1 ;;
esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: GNUsed.sh symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
seed_dir=$(CDPATH= cd -P -- "${entry%/*}" && pwd -P) || exit 1

gnu_sed_resolve()
(
    requested=$1
    [ -n "$requested" ] || exit 1
    case "$requested" in
        */*) candidate=$requested ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$requested" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" &&
                          pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-sed-adapter-probe 2>/dev/null || true)
    case "$identity" in
        whp-qemu-sed-seed-adapter|"$marker") exit 1 ;;
    esac
    identity=$("$candidate" --whp-gnu-sed-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        *'(GNU sed)'*) ;;
        *) exit 1 ;;
    esac
    printf '%s\n' "$candidate"
)

gnu_sed_probe()
(
    binary=$1
    # Verify ordinary sed semantics with the existing native seed contract.
    WHP_SED_SEED="$binary" /bin/sh "$seed_dir/sed.sh" \
        --print-seed >/dev/null 2>&1 || exit 1
    # GNU's --null-data must actually transform NUL-delimited records.
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-gnu-sed.XXXXXXXX") || exit 1
    trap 'rm -rf "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    printf 'alpha\000beta\000' > "$tmp/input"
    printf 'alpha\000gamma\000' > "$tmp/expected"
    "$binary" --null-data 's/beta/gamma/' "$tmp/input" \
        > "$tmp/actual" 2>/dev/null || exit 1
    cmp -s "$tmp/expected" "$tmp/actual"
)

gnu_sed_admit()
{
    binary=$(gnu_sed_resolve "$1") || return 1
    if [ "${probe:-yes}" = yes ]; then
        gnu_sed_probe "$binary" || {
            printf 'error: GNU sed capability probe failed: %s\n' "$binary" >&2
            return 1
        }
    fi
    printf '%s\n' "$binary"
}

gnu_sed_select()
{
    # Never inherit WHP_SED_SEED or SED: these belong to portable sed.
    for variable in WHP_GNU_SED_SEED GNUSED GSED; do
        case "$variable" in
            WHP_GNU_SED_SEED) requested=${WHP_GNU_SED_SEED:-} ;;
            GNUSED) requested=${GNUSED:-} ;;
            GSED) requested=${GSED:-} ;;
        esac
        [ -n "$requested" ] || continue
        if gnu_sed_admit "$requested"; then return 0; fi
        printf 'error: %s is not a usable GNU sed: %s\n' \
            "$variable" "$requested" >&2
        return 1
    done

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        provider=${WHP_MACOS_DEPENDENCY_PROVIDER:-auto}
        case "$provider" in
            homebrew|auto)
                if requested=$(/bin/sh "$seed_dir/brew.sh" \
                    --formula-bin gnu-sed gsed 2>/dev/null); then
                    if gnu_sed_admit "$requested"; then return 0; fi
                fi
                if [ "$provider" = homebrew ] ||
                   [ -n "${HOMEBREW_PREFIX:-}${WHP_BREW_SEED:-}${WHP_HOMEBREW_BREW:-}" ]; then
                    printf '%s\n' \
                        'error: selected Homebrew has no usable gnu-sed gsed' >&2
                    return 1
                fi ;;
        esac
        case "$provider" in
            macports|auto)
                requested=${MACPORTS_PREFIX:-/opt/local}/bin/gsed
                if gnu_sed_admit "$requested"; then return 0; fi
                if [ "$provider" = macports ]; then
                    printf 'error: selected MacPorts has no usable GNU sed: %s\n' \
                        "$requested" >&2
                    return 1
                fi ;;
            system)
                for requested in /usr/bin/sed /bin/sed; do
                    if gnu_sed_admit "$requested"; then return 0; fi
                done
                printf '%s\n' 'error: no GNU sed in selected system provider' >&2
                return 1 ;;
        esac
    fi
    for requested in gsed sed /usr/bin/sed; do
        if gnu_sed_admit "$requested"; then return 0; fi
    done
    printf '%s\n' 'error: no installed GNU sed passed required checks' >&2
    return 1
}

case "${1:-}" in
    --print-candidate) probe=no; gnu_sed_select ;;
    --print-seed|--print-gnused) probe=yes; gnu_sed_select ;;
    --check)
        probe=yes
        selected=$(gnu_sed_select) || exit 1
        printf 'WHP GNU sed seed: %s (portable sed and --null-data verified)\n' \
            "$selected" ;;
    *)
        # The full probe happens at admission, not on every forwarded call.
        probe=no
        selected=$(gnu_sed_select) || exit 1
        exec "$selected" "$@" ;;
esac
