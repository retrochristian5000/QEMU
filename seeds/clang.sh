#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Independent native Clang compiler seed. Never selects a guest/target CC.
# cc.sh can opt in through WHP_CLANG_SEED; no managed LLVM bootstrap cycle.
set -eu

marker=whp-qemu-clang-seed-adapter
case "${1:-}" in
    --whp-clang-adapter-probe|--whp-cc-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

# Resolve the checkout when launched via PATH or a symlink.
seed_entry=$0
case "$seed_entry" in
    */*) ;;
    *) seed_entry=$(command -v "$seed_entry") || exit 1 ;;
esac
seed_depth=0
while [ -L "$seed_entry" ]; do
    seed_depth=$((seed_depth + 1))
    [ "$seed_depth" -le 16 ] || {
        printf '%s\n' 'error: clang seed symlink loop' >&2
        exit 1
    }
    seed_link=$(readlink "$seed_entry") || exit 1
    case "$seed_link" in
        /*) seed_entry=$seed_link ;;
        *) seed_entry=${seed_entry%/*}/$seed_link ;;
    esac
done
seed_root=$(CDPATH= cd -P -- "${seed_entry%/*}/.." && pwd -P) || exit 1
. "$seed_root/scripts/whp-build/compiler-seed-common.sh"

# A working native C compiler is not necessarily Clang. Verify that the
# frontend actually defines Clang's identity macro, without grep or other
# managed host-tool dependencies.
clang_identity()
(
    candidate=$1
    [ "$(whp_native_compiler_identity "$candidate" c)" = clang ]
)

clang_admit()
{
    value=$1
    report=${2:-quiet}
    candidate=$(try_compiler c "$value" "$report") || return 1
    if ! clang_identity "$candidate"; then
        [ "$report" = report ] &&
            printf 'error: native C compiler is not a usable Clang frontend: %s\n' "$candidate" >&2
        return 1
    fi
    printf '%s\n' "$candidate"
}

clang_select()
{
    if [ -n "${WHP_CLANG_SEED:-}" ]; then
        if compiler=$(clang_admit "$WHP_CLANG_SEED" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: WHP_CLANG_SEED is not a native Clang compiler: %s\n' \
            "$WHP_CLANG_SEED" >&2
        return 1
    fi

    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        # Respect the selected Xcode/CLT. A wrong Apple developer root must
        # not be concealed by PATH or Homebrew fallback discovery.
        . "$seed_root/scripts/whp-build/macos-developer-tools.sh"
        value=$(whp_apple_find_tool clang) || return 1
        if compiler=$(clang_admit "$value" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: selected Apple Clang cannot build native tools: %s\n' "$value" >&2
        return 1
    fi

    for value in clang /usr/bin/clang; do
        if compiler=$(clang_admit "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable native Clang for the optional WHP seed' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-clang) clang_select; exit $? ;;
    --check)
        compiler=$(clang_select) || exit 1
        printf 'WHP native Clang seed: %s\n' "$compiler"
        exit 0 ;;
    --print-cxx|--check-cxx)
        printf '%s\n' 'error: use cxx.sh for C++' >&2
        exit 2 ;;
esac

compiler=$(clang_select) || exit 1
# Keep the runtime driver target identical to its validated native probe.
whp_native_target_environment
if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    # Use the exact SDK as the native C compile/link/run admission probe.
    seed_sdk=$(whp_native_sdkroot) || exit 1
    SDKROOT=$seed_sdk
    export SDKROOT
    exec "$compiler" -isysroot "$seed_sdk" "$@"
fi
exec "$compiler" "$@"
