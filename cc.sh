#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native C compiler seed adapter; target CC/CXX excluded.
set -eu
WHP_CC_ADAPTER_MARKER=whp-qemu-cc-seed-adapter
case "${1:-}" in
    --whp-cc-adapter-probe|--whp-cxx-adapter-probe)
        printf "%s\n" "$WHP_CC_ADAPTER_MARKER"; exit 0 ;;
esac

# Resolve physical script path even when invoked through a symlink.
seed_entry=$0
case "$seed_entry" in */*) ;; *) seed_entry=$(command -v "$seed_entry") ;; esac
seed_depth=0
while [ -L "$seed_entry" ]; do
    seed_depth=$((seed_depth + 1))
    [ "$seed_depth" -le 16 ] || { echo "error: compiler adapter symlink loop" >&2; exit 1; }
    seed_link=$(readlink "$seed_entry") || exit 1
    case "$seed_link" in
        /*) seed_entry=$seed_link ;;
        *) seed_entry=${seed_entry%/*}/$seed_link ;;
    esac
done
seed_root=$(CDPATH= cd -P -- "${seed_entry%/*}" && pwd -P) || exit 1
. "$seed_root/scripts/whp-build/compiler-seed-common.sh"
select_cc()
{
    for value in "${WHP_CC_SEED:-}" "${CC_FOR_BUILD:-}"; do
        [ -n "$value" ] || continue
        if compiler=$(try_compiler c "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: requested build C compiler is not native/usable: %s\n' "$value" >&2
        return 1
    done

    if command -v xcrun >/dev/null 2>&1; then
        value=$(xcrun --sdk macosx --find clang 2>/dev/null || true)
        if [ -n "$value" ] && compiler=$(try_compiler c "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    fi

    for value in cc clang gcc; do
        if compiler=$(try_compiler c "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    done

    printf '%s\n' 'error: no native host C compiler passed the QEMU bootstrap probe' >&2
    return 1
}

case "${1:-}" in
    --print-cc|--print-seed) select_cc; exit $? ;;
    --check) compiler=$(select_cc); printf "WHP C compiler seed: %s\n" "$compiler"; exit 0 ;;
    --print-cxx|--check-cxx|--cxx) echo "error: use cxx.sh for C++" >&2; exit 2 ;;
esac
compiler=$(select_cc)
exec "$compiler" "$@"
