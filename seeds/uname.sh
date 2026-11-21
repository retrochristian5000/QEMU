#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native build-machine uname seed. Never derives a compiler host/target triple.
# Prefer the system utility over PATH so a cross build cannot spoof the host.
set -eu

marker=whp-qemu-uname-seed-adapter
if [ "${1:-}" = --whp-uname-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

# A build host must provide native uname; this is not a GNU uname bootstrap.
# Keep the reference outside PATH so a cross-tool wrapper cannot replace it.
reference=
for candidate in /usr/bin/uname /bin/uname; do
    [ -f "$candidate" ] && [ -x "$candidate" ] || continue
    kernel=$("$candidate" -s 2>/dev/null) || continue
    machine=$("$candidate" -m 2>/dev/null) || continue
    release=$("$candidate" -r 2>/dev/null) || continue
    [ -n "$kernel" ] && [ -n "$machine" ] && [ -n "$release" ] || continue
    reference=$candidate
    break
done
[ -n "$reference" ] || {
    printf '%s\n' 'error: no usable system uname found at /usr/bin or /bin' >&2
    exit 1
}

selected=$reference
if [ -n "${WHP_UNAME_SEED:-}" ]; then
    case "$WHP_UNAME_SEED" in
        */*) selected=$WHP_UNAME_SEED ;;
        *[!a-zA-Z0-9_.+-]*|'')
            printf 'error: invalid WHP_UNAME_SEED executable: %s\n' "$WHP_UNAME_SEED" >&2
            exit 1 ;;
        *) selected=$(command -v "$WHP_UNAME_SEED" 2>/dev/null) || {
               printf 'error: WHP_UNAME_SEED was not found: %s\n' "$WHP_UNAME_SEED" >&2
               exit 1
           } ;;
    esac
    [ -f "$selected" ] && [ -x "$selected" ] || {
        printf 'error: WHP_UNAME_SEED is not executable: %s\n' "$selected" >&2
        exit 1
    }
    # Never recurse through this seed when an explicit selection names itself.
    identity=$("$selected" --whp-uname-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || {
        printf '%s\n' 'error: uname seed cannot select its own adapter' >&2
        exit 1
    }
    # Reject stale build/host architecture, OS, and Darwin kernel release.
    for option in -s -m -r; do
        reference_value=$("$reference" "$option") || exit 1
        selected_value=$("$selected" "$option" 2>/dev/null) || {
            printf 'error: selected uname cannot report %s\n' "$option" >&2
            exit 1
        }
        [ "$selected_value" = "$reference_value" ] || {
            printf 'error: selected uname disagrees with system %s: %s (expected %s)\n' \
                "$option" "$selected_value" "$reference_value" >&2
            exit 1
        }
    done
fi

# Resolve relative override spellings before consumers change directories.
case "$selected" in
    /*) ;;
    */*)
        directory=$(CDPATH= cd -P -- "${selected%/*}" && pwd -P) || exit 1
        selected=$directory/${selected##*/} ;;
    *)
        printf 'error: uname seed did not resolve an executable path: %s\n' "$selected" >&2
        exit 1 ;;
esac

case "${1:-}" in
    --print-seed|--print-uname)
        printf '%s\n' "$selected" ;;
    --check)
        printf 'WHP native uname seed: %s (%s/%s, release %s)\n' \
            "$selected" "$kernel" "$machine" "$release" ;;
    *) exec "$selected" "$@" ;;
esac
