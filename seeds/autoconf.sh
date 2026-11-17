#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native GNU Autoconf selector; shared pair validation lives in autom4te.sh.
# This adapter never builds Autoconf or promotes unfinished managed output.
set -eu

marker=whp-qemu-autoconf-seed-adapter
case "${1:-}" in
    --whp-autoconf-adapter-probe|--whp-autom4te-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

# Resolve symlink launchers back to this checkout, not their calling directory.
entry=$0
case "$entry" in
    */*) ;;
    *) entry=$(command -v "$entry") || exit 1 ;;
esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || {
        printf '%s\n' 'error: Autoconf seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$entry") || exit 1
    case "$link" in
        /*) entry=$link ;;
        *) entry=${entry%/*}/$link ;;
    esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1
pair_seed="$root/seeds/autom4te.sh"
[ -f "$pair_seed" ] || {
    printf 'error: GNU Autoconf pair seed is missing: %s\n' "$pair_seed" >&2
    exit 1
}

case "${1:-}" in
    --print-seed|--print-autoconf)
        exec /bin/sh "$pair_seed" --print-autoconf ;;
    --print-autom4te)
        exec /bin/sh "$pair_seed" --print-seed ;;
    --check)
        exec /bin/sh "$pair_seed" --check ;;
    *)
        exec /bin/sh "$pair_seed" --autoconf "$@" ;;
esac
