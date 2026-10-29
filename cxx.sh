#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native C++17 compiler seed adapter; target CC/CXX excluded.
set -eu
WHP_CC_ADAPTER_MARKER=whp-qemu-cxx-seed-adapter
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
derived_cxx_candidates()
{
    cc=$1
    dir=${cc%/*}
    base=${cc##*/}
    case "$base" in
        clang) printf '%s\n' "$dir/clang++" ;;
        clang-*) suffix=${base#clang-}; printf '%s\n' "$dir/clang++-$suffix" ;;
        gcc) printf '%s\n' "$dir/g++" ;;
        gcc-*) suffix=${base#gcc-}; printf '%s\n' "$dir/g++-$suffix" ;;
        cc) printf '%s\n' "$dir/c++" ;;
    esac
}

select_cxx()
{
    for value in "${WHP_CXX_SEED:-}" "${CXX_FOR_BUILD:-}"; do
        [ -n "$value" ] || continue
        if compiler=$(try_compiler c++ "$value" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: requested build C++ compiler is not native/C++17-capable: %s\n' "$value" >&2
        return 1
    done

    # The build-machine C++ compiler must first follow the selected C driver.
    # On macOS, trying xcrun before this pairing could silently mix a pinned
    # LLVM Clang C seed with an unrelated Apple Clang++ and even hide an invalid
    # explicit C seed from --print-cxx.
    cc=$("$seed_root/cc.sh" --print-cc) || return 1
    value=$(derived_cxx_candidates "$cc" 2>/dev/null || true)
    if [ -n "$value" ] && compiler=$(try_compiler c++ "$value"); then
        printf '%s\n' "$compiler"
        return 0
    fi

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        . "$seed_root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool clang++) || return 1
        if compiler=$(try_compiler c++ "$value" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: selected Apple C++ compiler cannot build native tools: %s\n' "$value" >&2
        return 1
    fi

    for value in c++ clang++ g++; do
        if compiler=$(try_compiler c++ "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    done

    printf '%s\n' 'error: no native host C++17 compiler passed the QEMU bootstrap probe' >&2
    return 1
}

case "${1:-}" in
    --print-cxx|--print-seed) select_cxx; exit $? ;;
    --check|--check-cxx) compiler=$(select_cxx); printf "WHP C++ compiler seed: %s\n" "$compiler"; exit 0 ;;
    --print-cc|--cc) echo "error: use cc.sh for C" >&2; exit 2 ;;
esac
compiler=$(select_cxx)
exec "$compiler" "$@"
