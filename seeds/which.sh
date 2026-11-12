#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Portable executable lookup seed for QEMU bootstrap helpers.
# No dependency on an external which, Python, managed tools, or other seeds.
# This locates executable files, not shell aliases/functions/builtins. Shell
# scripts needing those should continue to use POSIX 'command -v'.
set -eu

marker=whp-qemu-which-seed-adapter
if [ "${1:-}" = --whp-which-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

seed_path()
(
    entry=$0
    case "$entry" in
        */*) ;;
        *) entry=$(command -v "$entry") || exit 1 ;;
    esac
    depth=0
    while [ -L "$entry" ]; do
        depth=$((depth + 1))
        [ "$depth" -le 16 ] || {
            printf '%s\n' 'error: which seed symlink loop' >&2
            exit 1
        }
        link=$(readlink "$entry") || exit 1
        case "$link" in
            /*) entry=$link ;;
            *) entry=${entry%/*}/$link ;;
        esac
    done
    directory=$(CDPATH= cd -P -- "${entry%/*}" && pwd -P) || exit 1
    printf '%s/%s\n' "$directory" "${entry##*/}"
)

# Keep provenance discovery independent of PATH search and the lookup options.
case "${1:-}" in
    --print-seed|--print-which)
        seed_path
        exit $? ;;
    --check)
        selected=$(seed_path) || exit 1
        [ -f "$selected" ] && [ -r "$selected" ] || exit 1
        printf 'WHP native which seed: %s\n' "$selected"
        exit 0 ;;
esac

all=0
silent=0
while [ "$#" -gt 0 ]; do
    case "$1" in
        -a) all=1; shift ;;
        -s) silent=1; shift ;;
        --) shift; break ;;
        -*)
            printf 'error: unsupported which option: %s\n' "$1" >&2
            exit 2 ;;
        *) break ;;
    esac
done
if [ "$#" -eq 0 ]; then
    printf '%s\n' 'usage: which.sh [-a] [-s] [--] command ...' >&2
    exit 2
fi

# Search each PATH component without splitting on spaces or glob characters.
# Empty PATH components mean the current directory. Resolve relative matches
# to absolute paths so consumers can safely change their working directory.
lookup()
(
    name=$1
    case "$name" in
        */*)
            [ -f "$name" ] && [ -x "$name" ] || exit 1
            if [ "$silent" -eq 0 ]; then
                case "$name" in
                    /*) printf '%s\n' "$name" ;;
                    *)
                        directory=$(CDPATH= cd -P -- "${name%/*}" && pwd -P) || exit 1
                        printf '%s/%s\n' "$directory" "${name##*/}"
                        ;;
                esac
            fi
            exit 0 ;;
    esac

    remaining=${PATH-}
    found=0
    while :; do
        case "$remaining" in
            *:*) part=${remaining%%:*}; remaining=${remaining#*:}; more=1 ;;
            *) part=$remaining; more=0 ;;
        esac
        [ -n "$part" ] || part=.
        candidate=$part/$name
        if [ -f "$candidate" ] && [ -x "$candidate" ]; then
            found=1
            if [ "$silent" -eq 0 ]; then
                case "$candidate" in
                    /*) printf '%s\n' "$candidate" ;;
                    *)
                        directory=$(CDPATH= cd -P -- "$part" && pwd -P) || exit 1
                        printf '%s/%s\n' "$directory" "$name"
                        ;;
                esac
            fi
            [ "$all" -eq 1 ] || exit 0
        fi
        [ "$more" -eq 1 ] || break
    done
    [ "$found" -eq 1 ]
)

status=0
for name do
    lookup "$name" || status=1
done
exit "$status"
