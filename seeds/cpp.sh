#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Host C preprocessor seed bridge. Never promote this to target CPP.
# Reuse a validated native compiler driver with -E; do not discover a
# mismatched system cpp or the LLVM toolchain being bootstrapped.
set -eu

WHP_CPP_ADAPTER_MARKER=whp-qemu-cpp-seed-adapter
if [ "${1:-}" = --whp-cpp-adapter-probe ]; then
    printf '%s\n' "$WHP_CPP_ADAPTER_MARKER"
    exit 0
fi

# Keep this bridge anchored to its checkout even when called via a symlink.
seed_entry=$0
case "$seed_entry" in
    */*) ;;
    *) seed_entry=$(command -v "$seed_entry" 2>/dev/null || true) ;;
esac
[ -n "$seed_entry" ] || exit 1
seed_depth=0
while [ -L "$seed_entry" ]; do
    seed_depth=$((seed_depth + 1))
    [ "$seed_depth" -le 16 ] || {
        printf '%s\n' 'error: C preprocessor adapter symlink loop' >&2
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

cpp_is_self()
{
    marker=$("$1" --whp-cpp-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_CPP_ADAPTER_MARKER" ]
}

# Test macro expansion without a host grep/sed dependency or a link step.
cpp_semantic_probe()
(
    candidate=$1
    whp_native_probe_environment
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        sdk=$(whp_native_sdkroot) || exit 1
        set -- -isysroot "$sdk"
    else
        set --
    fi
    result=$(printf '%s\n' \
        '#define WHP_CPP_PROBE whp_cpp_seed_ok_417' \
        'WHP_CPP_PROBE' |
        "$candidate" "$@" -E -P -x c - 2>/dev/null) || exit 1
    # Clang may emit an initial empty line with -P; the final token must match.
    case "$result" in
        whp_cpp_seed_ok_417|*'
whp_cpp_seed_ok_417') exit 0 ;;
    esac
    exit 1
)

# Homebrew Clang is an opt-in host preprocessor, never a silent override
# of the native C driver chosen by cc.sh. LLVM is usually keg-only.
select_homebrew_cpp()
{
    for candidate in \
        "${HOMEBREW_PREFIX:-/opt/homebrew}/opt/llvm/bin/clang" \
        "${HOMEBREW_PREFIX:-/opt/homebrew}/bin/clang" \
        /opt/homebrew/opt/llvm/bin/clang \
        /usr/local/opt/llvm/bin/clang \
        /opt/homebrew/bin/clang \
        /usr/local/bin/clang; do
        [ -x "$candidate" ] || continue
        if driver=$(try_compiler c "$candidate" report) &&
           cpp_semantic_probe "$driver"; then
            printf '%s\n' "$driver"
            return 0
        fi
        # The first installed Homebrew candidate is authoritative. Do not
        # hide its failure by silently switching developer toolchains.
        printf 'error: selected Homebrew CPP is not native/usable: %s\n' "$candidate" >&2
        return 1
    done
    printf '%s\n' 'error: no usable native Homebrew Clang for WHP CPP' >&2
    return 1
}

select_seed()
{
    if [ -n "${WHP_CPP_SEED:-}" ]; then
        # Detect our own marker before the shared resolver invokes --version;
        # otherwise a cpp.sh override could recursively re-enter selection.
        case "$WHP_CPP_SEED" in
            */*) driver=$WHP_CPP_SEED ;;
            *[[:space:]]*)
                printf 'error: WHP_CPP_SEED must name one executable: %s\n' "$WHP_CPP_SEED" >&2
                return 1 ;;
            *) driver=$(command -v "$WHP_CPP_SEED" 2>/dev/null || true) ;;
        esac
        [ -n "$driver" ] && [ -x "$driver" ] || {
            printf 'error: WHP_CPP_SEED is not executable: %s\n' "$WHP_CPP_SEED" >&2
            return 1
        }
        if cpp_is_self "$driver"; then
            printf '%s\n' 'error: WHP_CPP_SEED refers to the cpp.sh bridge itself' >&2
            return 1
        fi
        driver=$(resolve_executable "$WHP_CPP_SEED" report) || return 1
        # An explicitly chosen different compiler must still be host-native.
        if [ "$driver" != "${CC_FOR_BUILD:-}" ]; then
            driver=$(try_compiler c "$driver" report) || return 1
        fi
    else
        case "${WHP_CPP_PREFER_HOMEBREW:-0}" in
            0)
                # cc.sh already probes native compilation, linkage and SDK.
                driver=$("$seed_root/seeds/cc.sh" --print-cc) || return 1
                ;;
            1)
                [ "$(uname -s 2>/dev/null || true)" = Darwin ] || {
                    printf '%s\n' 'error: Homebrew CPP preference is macOS-only' >&2
                    return 1
                }
                driver=$(select_homebrew_cpp) || return 1
                ;;
            *)
                printf '%s\n' 'error: WHP_CPP_PREFER_HOMEBREW must be 0 or 1' >&2
                return 1
                ;;
        esac
    fi
    if ! cpp_semantic_probe "$driver"; then
        printf 'error: native C preprocessor probe failed: %s\n' "$driver" >&2
        return 1
    fi
    printf '%s\n' "$driver"
}

case "${1:-}" in
    --print-cpp|--print-seed)
        select_seed
        exit $? ;;
    --check)
        driver=$(select_seed) || exit 1
        printf 'WHP C preprocessor seed: %s (-E)\n' "$driver"
        exit 0 ;;
esac

# A build invocation validates exactly once, before managed LLVM starts.
# The locked hot path never compiles a new probe for each preprocessing call.
if [ "${WHP_CPP_LOCKED:-0}" = 1 ] && [ -n "${WHP_CPP_SEED:-}" ]; then
    driver=$WHP_CPP_SEED
    case "$driver" in
        "$seed_root/seeds/cpp.sh"|*/seeds/cpp.sh)
            printf '%s\n' 'error: locked C preprocessor points at cpp.sh' >&2
            exit 1 ;;
    esac
    [ -x "$driver" ] || {
        printf 'error: locked C preprocessor is not executable: %s\n' "$driver" >&2
        exit 1
    }
else
    driver=$(select_seed) || exit 1
fi

# Keep the same selected macOS SDK as cc.sh; target CPP/CPPFLAGS are untouched.
if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
    sdk=$(whp_native_sdkroot) || exit 1
    SDKROOT=$sdk
    export SDKROOT
    exec "$driver" -isysroot "$sdk" -E "$@"
fi
exec "$driver" -E "$@"
