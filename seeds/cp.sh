#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# POSIX copy seed: resolve one host implementation for the QEMU bootstrap.
set -eu

WHP_CP_ADAPTER_MARKER=whp-qemu-cp-seed-adapter
if [ "${1:-}" = --whp-cp-adapter-probe ]; then
    printf '%s\n' "$WHP_CP_ADAPTER_MARKER"
    exit 0
fi

cp_self()
{
    marker=$("$1" --whp-cp-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_CP_ADAPTER_MARKER" ]
}

cp_probe()
(
    candidate=$1
    probe_dir=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-cp-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$probe_dir"' 0
    trap 'exit 1' 1 2 3 15
    mkdir "$probe_dir/source" || exit 1
    printf 'whp-copy-probe\n' > "$probe_dir/source/value" || exit 1
    "$candidate" "$probe_dir/source/value" "$probe_dir/single" || exit 1
    [ "$(cat "$probe_dir/single")" = whp-copy-probe ] || exit 1
    "$candidate" -R "$probe_dir/source" "$probe_dir/recursive" || exit 1
    [ "$(cat "$probe_dir/recursive/value")" = whp-copy-probe ] || exit 1
    "$candidate" -p "$probe_dir/source/value" "$probe_dir/preserved" || exit 1
    [ "$(cat "$probe_dir/preserved")" = whp-copy-probe ] || exit 1
)

cp_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null || true) ;;
    esac
    [ -n "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
             candidate=$directory/${candidate##*/} ;;
        *) exit 1 ;;
    esac
    cp_self "$candidate" && exit 3
    cp_probe "$candidate" || exit 1
    printf '%s\n' "$candidate"
)

cp_select()
{
    if [ -n "${WHP_CP_SEED:-}" ]; then
        if seed=$(cp_resolve "$WHP_CP_SEED"); then
            printf '%s\n' "$seed"
            return 0
        fi
        printf 'error: WHP_CP_SEED is not a usable host cp: %s\n' "$WHP_CP_SEED" >&2
        return 1
    fi
    for candidate in /bin/cp /usr/bin/cp cp; do
        if seed=$(cp_resolve "$candidate"); then
            printf '%s\n' "$seed"
            return 0
        fi
    done
    printf '%s\n' 'error: no host cp passed the QEMU copy seed probe' >&2
    return 1
}

case "${1:-}" in
    --print-seed) cp_select; exit $? ;;
    --check)
        seed=$(cp_select) || exit 1
        printf 'WHP cp seed: %s\n' "$seed"
        exit 0 ;;
esac

if [ "${WHP_CP_LOCKED:-0}" = 1 ]; then
    [ -n "${WHP_CP_SEED:-}" ] || {
        printf '%s\n' 'error: locked cp has no selected seed' >&2
        exit 1
    }
    case "$WHP_CP_SEED" in
        */cp.sh|*/scripts/whp-build/seed-bin/cp)
            printf '%s\n' 'error: locked cp points back to its seed adapter' >&2
            exit 1 ;;
    esac
    [ -x "$WHP_CP_SEED" ] || exit 1
    exec "$WHP_CP_SEED" "$@"
fi
seed=$(cp_select) || exit 1
exec "$seed" "$@"
