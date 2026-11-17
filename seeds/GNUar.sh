#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional installed GNU Binutils ar seed. Not an alias for generic ar or LLVM ar.
# It never bootstraps binutils, GCC, or a target toolchain.
set -eu

marker=whp-qemu-gnu-ar-seed-adapter
case "${1:-}" in
    --whp-gnu-ar-adapter-probe|--whp-ar-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

archive_verbose=${WHP_ARCHIVE_VERBOSE:-0}
case "$archive_verbose" in
    0|1) ;;
    *) printf 'error: WHP_ARCHIVE_VERBOSE must be 0 or 1: %s\n' "$archive_verbose" >&2; exit 2 ;;
esac

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: GNU ar seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1

resolve_gnu_ar()
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
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    # Detect both adapters before invoking --version. This prevents a
    # GNUar.sh symlink from recursing and rejects generic ar.sh as a provider.
    identity=$("$candidate" --whp-ar-adapter-probe 2>/dev/null || true)
    case "$identity" in
        "$marker"|whp-qemu-ar-seed-adapter) exit 1 ;;
    esac
    banner=$(LC_ALL=C "$candidate" --version 2>/dev/null) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        'GNU ar ('*'GNU Binutils'*') '*) ;;
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
    printf '%s\n' "$candidate"
)

# Reuse the generic seed's full native-object/link probe; the GNU-specific
# seed only adds the provider-identity constraint and selection policy.
native_probe()
{
    WHP_AR_SEED="$1" AR_FOR_BUILD= \
        /bin/sh "$root/seeds/ar.sh" --print-seed >/dev/null
}

admit()
{
    requested=$1
    provider=$2
    candidate=$(resolve_gnu_ar "$requested") || return 1
    if [ "${probe:-yes}" = yes ]; then
        native_probe "$candidate" || {
            printf 'error: GNU ar native archive probe failed: %s\n' "$candidate" >&2
            return 1
        }
    fi
    if [ "$archive_verbose" = 1 ]; then
        printf 'WHP GNU ar selection: provider=%s; executable=%s; native-probe=%s\n' \
            "$provider" "$candidate" "${probe:-yes}" >&2
    fi
    printf '%s\n' "$candidate"
}

select_seed()
{
    # Deliberately distinct from WHP_AR_SEED / AR_FOR_BUILD / guest AR.
    # An invalid explicit provider is authoritative: never fall back.
    if [ -n "${WHP_GNU_AR_SEED:-}" ]; then
        if selected=$(admit "$WHP_GNU_AR_SEED" WHP_GNU_AR_SEED); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: WHP_GNU_AR_SEED is not a usable native GNU Binutils ar: %s\n' \
            "$WHP_GNU_AR_SEED" >&2
        return 1
    fi

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        if [ -n "${HOMEBREW_PREFIX:-}" ]; then
            brew_prefix=$HOMEBREW_PREFIX
        else
            case "$(uname -m 2>/dev/null || true)" in
                arm64|arm64e|aarch64) brew_prefix=/opt/homebrew ;;
                x86_64) brew_prefix=/usr/local ;;
                *) brew_prefix= ;;
            esac
        fi
        if [ -n "$brew_prefix" ]; then
            for requested in "$brew_prefix/opt/binutils/bin/gar" \
                             "$brew_prefix/bin/gar"; do
                if selected=$(admit "$requested" "Homebrew:$requested"); then
                    printf '%s\n' "$selected"
                    return 0
                fi
            done
        fi
        macports_prefix=${MACPORTS_PREFIX:-/opt/local}
        if selected=$(admit "$macports_prefix/bin/gar" "MacPorts:$macports_prefix"); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    # GNU tools may be exposed by their unprefixed name on Linux or gar on
    # macOS. Reject Apple and LLVM ar on identity, even if they implement rcs.
    for requested in gar ar /usr/bin/ar; do
        if selected=$(admit "$requested" "PATH:$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no installed native GNU Binutils ar passed validation (optional seed)' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-gnu-ar)
        probe=yes
        select_seed ;;
    --print-candidate)
        # Identity-only lookup, not a native archive compatibility guarantee.
        probe=no
        select_seed ;;
    --check)
        probe=yes
        selected=$(select_seed) || exit 1
        printf 'WHP installed GNU ar seed: %s (GNU Binutils; native archive/link verified)\n' \
            "$selected" ;;
    *)
        probe=no
        selected=$(select_seed) || exit 1
        if [ "$archive_verbose" = 1 ]; then
            printf 'WHP GNU ar invocation: executable=%s; operation=%s; archive=%s; argument-count=%s; admission=not-repeated\n' \
                "$selected" "${1:-<none>}" "${2:-<none>}" "$#" >&2
        fi
        exec "$selected" "$@" ;;
esac
