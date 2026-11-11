#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native GNU Make seed. The pinned Make fork cannot bootstrap itself.
set -eu

marker=whp-qemu-make-seed-adapter
if [ "${1:-}" = --whp-make-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: GNU Make seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1
. "$root/scripts/whp-build/gnu-make.bash"

resolve_seed()
(
    for setting in WHP_MAKE_SEED MAKE_CMD MAKE; do
        case "$setting" in
            WHP_MAKE_SEED) requested=${WHP_MAKE_SEED:-} ;;
            MAKE_CMD) requested=${MAKE_CMD:-} ;;
            MAKE) requested=${MAKE:-} ;;
        esac
        [ -n "$requested" ] || continue
        selected=$(whp_resolve_gnu_make "$requested") || {
            printf 'error: invalid native GNU Make %s: %s\n' "$setting" "$requested" >&2
            exit 1
        }
        identity=$("$selected" --whp-make-adapter-probe 2>/dev/null || true)
        [ "$identity" != "$marker" ] || {
            printf 'error: GNU Make seed recurses into itself: %s\n' "$selected" >&2
            exit 1
        }
        printf '%s\n' "$selected"
        exit 0
    done

    selected=$(whp_find_gnu_make) || {
        printf '%s\n' 'error: no native GNU Make seed is available' >&2
        exit 1
    }
    identity=$("$selected" --whp-make-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || {
        printf '%s\n' 'error: GNU Make seed recursion through PATH' >&2
        exit 1
    }
    printf '%s\n' "$selected"
)

case "${1:-}" in
    --print-seed|--print-make) resolve_seed ;;
    --check)
        selected=$(resolve_seed) || exit 1
        printf 'WHP native GNU Make seed: %s\n' "$selected"
        ;;
    *)
        selected=$(resolve_seed) || exit 1
        exec "$selected" "$@"
        ;;
esac
