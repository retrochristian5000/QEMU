#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native Clang preprocessor selector. Never selects guest/target CPP.
# A dedicated clang-cpp need not be a working C compiler/linker.
set -eu

marker=whp-qemu-clang-cpp-seed-adapter
if [ "${1:-}" = --whp-clang-cpp-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

entry=$0
case "$entry" in */*) ;; *) entry=$(command -v "$entry") || exit 1 ;; esac
depth=0
while [ -L "$entry" ]; do
    depth=$((depth + 1))
    [ "$depth" -le 16 ] || { printf '%s\n' 'error: clang-cpp seed symlink loop' >&2; exit 1; }
    link=$(readlink "$entry") || exit 1
    case "$link" in /*) entry=$link ;; *) entry=${entry%/*}/$link ;; esac
done
root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || exit 1
. "$root/scripts/whp-build/compiler-seed-common.sh"

select_driver()
{
    if [ -n "${WHP_CLANG_CPP_SEED:-}" ]; then
        value=$WHP_CLANG_CPP_SEED
    else
        # Prefer the dedicated preprocessor beside the validated native CC.
        cc=$("$root/seeds/cc.sh" --print-cc) || return 1
        value=${cc%/*}/clang-cpp
    fi
    candidate=$(resolve_executable "$value" report) || return 1
    case "${candidate##*/}" in
        clang-cpp|clang-cpp-[0-9]* ) ;;
        *) printf 'error: native clang-cpp seed requires a dedicated clang-cpp executable: %s\n' "$candidate" >&2; return 1 ;;
    esac
    # Do not admit arbitrary cpp/gcc installations or recursive adapters.
    if [ "$("$candidate" --whp-clang-cpp-adapter-probe 2>/dev/null || true)" = "$marker" ]; then
        printf '%s\n' 'error: clang-cpp seed recursion' >&2
        return 1
    fi
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        sdk=$(whp_native_sdkroot) || return 1
        set -- -isysroot "$sdk"
    else
        set --
    fi
    output=$(printf '#define WHP_CLANG_CPP_PROBE 719\nWHP_CLANG_CPP_PROBE\n' |
        "$candidate" "$@" -E -P -x c - 2>/dev/null) || {
        printf 'error: clang-cpp failed preprocessing probe: %s\n' "$candidate" >&2
        return 1
    }
    case "$output" in 719|*'
719') ;; *)
        printf 'error: clang-cpp produced unexpected preprocessing output: %s\n' "$candidate" >&2
        return 1 ;;
    esac
    printf '%s\n' "$candidate"
}

case "${1:-}" in
    --print-seed|--print-cpp) select_driver; exit $? ;;
    --check)
        driver=$(select_driver) || exit 1
        printf 'WHP native clang-cpp: %s\n' "$driver"
        exit 0 ;;
esac

# Admission is for selection, not each preprocessing invocation. cpp.sh
# supplies the matching SDK and -E for the normal locked build path.
driver=$(select_driver) || exit 1
if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    sdk=$(whp_native_sdkroot) || exit 1
    SDKROOT=$sdk
    export SDKROOT
    exec "$driver" -isysroot "$sdk" -E "$@"
fi
exec "$driver" -E "$@"
