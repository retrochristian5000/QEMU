#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Optional native GNU C++ seed. Never replace the generic CXX_FOR_BUILD choice.
# In particular, Apple's g++ can be Clang; the executable name is not proof.
set -eu

marker=whp-qemu-gxx-seed-adapter
case "${1:-}" in
    --whp-gxx-adapter-probe|--whp-cxx-adapter-probe|--whp-cc-adapter-probe)
        printf '%s\n' "$marker"
        exit 0 ;;
esac

# Follow symlinked launchers so the shared native compiler probe and macOS
# SDK selection are always sourced from the same QEMU checkout.
seed_entry=$0
case "$seed_entry" in
    */*) ;;
    *) seed_entry=$(command -v "$seed_entry") || exit 1 ;;
esac
seed_depth=0
while [ -L "$seed_entry" ]; do
    seed_depth=$((seed_depth + 1))
    [ "$seed_depth" -le 16 ] || {
        printf '%s\n' 'error: GNU C++ seed symlink loop' >&2
        exit 1
    }
    link=$(readlink "$seed_entry") || exit 1
    case "$link" in
        /*) seed_entry=$link ;;
        *) seed_entry=${seed_entry%/*}/$link ;;
    esac
done
seed_root=$(CDPATH= cd -P -- "${seed_entry%/*}/.." && pwd -P) || exit 1
. "$seed_root/scripts/whp-build/compiler-seed-common.sh"

# __GNUC__ alone does NOT identify GNU C++: Clang provides compatibility
# macros. Require both GNU C++ macros, exclude known impersonating frontends,
# and verify the actual GCC driver reports itself as "gcc version ...".
gxx_frontend()
(
    candidate=$1
    whp_native_probe_environment
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        seed_sdk=$(whp_native_sdkroot) || exit 1
        set -- -isysroot "$seed_sdk"
    else
        set --
    fi
    macros=$("$candidate" "$@" -dM -E -x c++ - </dev/null 2>/dev/null) || exit 1
    case "$macros" in
        *'#define __clang__ '*|*'#define __INTEL_COMPILER '*|*'#define __INTEL_LLVM_COMPILER '*|*'#define __NVCOMPILER '*|*'#define __PGI '*|*'#define __EMSCRIPTEN__ '*)
            exit 1 ;;
    esac
    case "$macros" in *'#define __GNUC__ '*) ;; *) exit 1 ;; esac
    case "$macros" in *'#define __GNUG__ '*) ;; *) exit 1 ;; esac
    version=$("$candidate" -v 2>&1) || exit 1
    case "$version" in
        *'gcc version '*) exit 0 ;;
        *) exit 1 ;;
    esac
)

# The generic C++17 probe verifies headers, native linking and execution.
# Additionally link a real C++ standard-library program: gcc -x c++ without
# a working C++ runtime must not be admitted as g++.
gxx_stdlib()
(
    candidate=$1
    report=${2:-quiet}
    whp_native_probe_environment
    tmp=$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-gxx-seed.XXXXXX") || exit 1
    trap 'rm -rf -- "$tmp"' 0
    trap 'exit 1' 1 2 3 15
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        seed_sdk=$(whp_native_sdkroot) || exit 1
        set -- -isysroot "$seed_sdk"
    else
        set --
    fi
    printf '%s\n' \
        '#include <string>' \
        '#include <vector>' \
        'int main() {' \
        '    const std::string name("native GNU C++");' \
        '    std::vector<std::string> items(2, name);' \
        '    return items.at(1) == name ? 0 : 1;' \
        '}' > "$tmp/probe.cc" || exit 1
    if "$candidate" "$@" -std=c++17 "$tmp/probe.cc" -o "$tmp/probe" \
            >"$tmp/log" 2>&1 && "$tmp/probe" >>"$tmp/log" 2>&1; then
        exit 0
    fi
    if [ "$report" = report ]; then
        printf 'error: GNU C++17 standard-library link/run probe failed: %s\n' \
            "$candidate" >&2
        cat "$tmp/log" >&2
    fi
    exit 1
)

gxx_admit()
{
    value=$1
    detail=${2:-quiet}
    candidate=$(try_compiler c++ "$value" "$detail") || return 1
    if ! gxx_frontend "$candidate"; then
        [ "$detail" != report ] ||
            printf 'error: native C++ compiler is not the GNU GCC frontend: %s\n' \
                "$candidate" >&2
        return 1
    fi
    gxx_stdlib "$candidate" "$detail" || return 1
    printf '%s\n' "$candidate"
}

select_gxx()
{
    # WHP_GXX_SEED/GXX are GNU-specific. Do not inherit generic WHP_CXX_SEED,
    # CXX_FOR_BUILD or guest CXX, and do not silently replace Clang in QEMU.
    if [ -n "${WHP_GXX_SEED:-}" ] && [ -n "${GXX:-}" ] &&
       [ "$WHP_GXX_SEED" != "$GXX" ]; then
        printf 'warning: WHP_GXX_SEED overrides conflicting GXX: %s != %s\n' \
            "$WHP_GXX_SEED" "$GXX" >&2
    fi
    for role in WHP_GXX_SEED GXX; do
        case "$role" in
            WHP_GXX_SEED) requested=${WHP_GXX_SEED:-} ;;
            GXX) requested=${GXX:-} ;;
        esac
        [ -n "$requested" ] || continue
        if compiler=$(gxx_admit "$requested" report); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: %s is not a native GNU G++ compiler: %s\n' \
            "$role" "$requested" >&2
        return 1
    done

    # Versioned GNU installations are common on macOS, where /usr/bin/g++
    # is usually an Apple Clang compatibility name, not GNU GCC.
    for requested in g++ g++-17 g++-16 g++-15 g++-14 g++-13 g++-12 \
                     g++-11 g++-10 g++-mp-17 g++-mp-16 g++-mp-15 \
                     g++-mp-14 g++-mp-13 g++-mp-12; do
        if compiler=$(gxx_admit "$requested"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    done
    printf '%s\n' \
        'error: no native GNU G++ compiler found; set WHP_GXX_SEED or GXX to an installed GNU C++ driver' >&2
    return 1
}

case "${1:-}" in
    --print-gxx|--print-seed)
        select_gxx
        exit $? ;;
    --check)
        compiler=$(select_gxx) || exit 1
        printf 'WHP GNU C++ compiler seed: %s (GCC frontend, C++17 standard library verified)\n' \
            "$compiler"
        exit 0 ;;
    --print-cxx|--check-cxx|--print-cc)
        printf '%s\n' 'error: use cxx.sh for generic C++, cc.sh for C' >&2
        exit 2 ;;
esac

# A locked GNU provider avoids repeating compile/link probes for each call,
# but must not route back into a seed adapter, including a symlinked adapter.
if [ "${WHP_GXX_LOCKED:-0}" = 1 ]; then
    compiler=${WHP_GXX_SEED:-}
    if [ -z "$compiler" ] || [ ! -x "$compiler" ] || is_self "$compiler"; then
        printf '%s\n' 'error: locked GNU G++ has no independent executable' >&2
        exit 1
    fi
else
    compiler=$(select_gxx) || exit 1
fi
if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    seed_sdk=$(whp_native_sdkroot) || exit 1
    SDKROOT=$seed_sdk
    export SDKROOT
    exec "$compiler" -isysroot "$seed_sdk" "$@"
fi
exec "$compiler" "$@"
