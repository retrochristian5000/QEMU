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
seed_root=$(CDPATH= cd -P -- "${seed_entry%/*}/.." && pwd -P) || exit 1
. "$seed_root/scripts/whp-build/compiler-seed-common.sh"
. "$seed_root/scripts/whp-build/compiler-seed-session.sh"
select_cc()
{
    for value in "${WHP_CC_SEED:-}" "${CC_FOR_BUILD:-}"; do
        [ -n "$value" ] || continue
        if compiler=$(try_compiler c "$value" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: requested build C compiler is not native/usable: %s\n' "$value" >&2
        return 1
    done

    # A caller may select an independent, validated Clang rather than an
    # executable named cc. Existing explicit C compiler choices win.
    if [ -n "${WHP_CLANG_SEED:-}" ]; then
        compiler=$("$seed_root/seeds/clang.sh" --print-clang) || return 1
        printf '%s\n' "$compiler"
        return 0
    fi

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        # Invalid Xcode/CLT selection must not silently fall back to PATH.
        . "$seed_root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool clang) || return 1
        if compiler=$(try_compiler c "$value" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: selected Apple C compiler cannot build native tools: %s\n' "$value" >&2
        return 1
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

select_cc_for_build()
{
    whp_cc_session_lookup || select_cc
}

case "${1:-}" in
    --print-cc|--print-seed) select_cc_for_build; exit $? ;;
    --check)
        compiler=$(select_cc) || exit 1
        identity=$(whp_native_compiler_identity "$compiler" c)
        printf 'WHP C compiler seed: %s (frontend: %s)\n' "$compiler" "$identity"
        exit 0 ;;
    --print-cxx|--check-cxx|--cxx) echo "error: use cxx.sh for C++" >&2; exit 2 ;;
esac
compiler=$(select_cc_for_build)
# The compiler's real invocation must match the target-clean admission probe.
whp_native_target_environment
if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    # The admission probe used -isysroot; carry the exact validated SDK
    # into the real invocation too. Never let Clang silently fall back
    # to a different SDK (or fail to find libSystem).
    seed_sdk=$(whp_native_sdkroot) || exit 1
    SDKROOT=$seed_sdk
    export SDKROOT
    exec "$compiler" -isysroot "$seed_sdk" "$@"
fi
exec "$compiler" "$@"
