#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native Apple Mach-O linker; not GNU ld, LLD or a cross-linker.
set -eu

case "${1:-}" in
    --whp-apple-ld-adapter-probe)
        printf '%s\n' whp-qemu-apple-ld-seed-adapter
        exit 0 ;;
    --whp-ld-adapter-probe)
        # The generic seed must not recursively admit this adapter.
        printf '%s\n' whp-qemu-ld-seed-adapter
        exit 0 ;;
esac

if [ "$(uname -s)" != Darwin ]; then
    case "${1:-}" in
        --check)
            printf '%s\n' 'WHP Apple linker seed: not applicable (non-macOS)'
            exit 0 ;;
    esac
    printf '%s\n' 'error: Appleld.sh requires a native macOS host' >&2
    exit 1
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: Apple linker seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1
. "$root/scripts/whp-build/macos-developer-tools.sh"

apple_ld_identity()
(
    candidate=$1
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    marker=$("$candidate" --whp-ld-adapter-probe 2>/dev/null || true)
    [ "$marker" != whp-qemu-ld-seed-adapter ] || exit 1
    banner=$(LC_ALL=C "$candidate" -v 2>&1) || exit 1
    first=${banner%%'
'*}
    case "$first" in
        '@(#)PROGRAM:ld PROJECT:ld-'[0-9]*|\
        '@(#)PROGRAM:ld PROJECT:ld64-'[0-9]*|\
        '@(#)PROGRAM:ld-classic PROJECT:ld64-'[0-9]*)
            printf '%s\n' "$first" ;;
        *) exit 1 ;;
    esac
)

select_apple_ld()
(
    if [ -n "${WHP_APPLE_LD_SEED:-}" ]; then
        candidate=$WHP_APPLE_LD_SEED
        case "$candidate" in
            */*) ;;
            *[[:space:]]*) exit 1 ;;
            *) candidate=$(command -v "$candidate" 2>/dev/null) || exit 1 ;;
        esac
        case "$candidate" in
            /*) ;;
            */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
            *) exit 1 ;;
        esac
    else
        candidate=$(whp_apple_find_tool ld system) || exit 1
    fi

    if ! apple_ld_identity "$candidate" >/dev/null; then
        printf 'error: selected linker is not an Apple Mach-O linker: %s\n' "$candidate" >&2
        exit 1
    fi
    if [ "$probe" = yes ]; then
        # Reuse the generic seed's native object/link check. Never admit an
        # unrelated LD_FOR_BUILD or turn the optional seed into target LD.
        if ! WHP_LD_SEED="$candidate" LD_FOR_BUILD= \
            /bin/sh "$root/seeds/ld.sh" --print-ld >/dev/null; then
            printf 'error: Apple linker failed native relocatable link probe: %s\n' "$candidate" >&2
            exit 1
        fi
    fi
    printf '%s\n' "$candidate"
)

case "${1:-}" in
    --print-seed|--print-ld)
        probe=yes
        select_apple_ld ;;
    --check)
        probe=yes
        selected=$(select_apple_ld) || exit 1
        printf 'WHP Apple linker seed: %s (%s)\n' \
            "$selected" "$(apple_ld_identity "$selected")" ;;
    *)
        # Keep identity validation, but do not compile a new smoke object on
        # each link. Forward the caller's arguments unchanged.
        probe=no
        selected=$(select_apple_ld) || exit 1
        exec "$selected" "$@" ;;
esac
