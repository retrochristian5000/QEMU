#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
#
# Native compiler seed adapter for the WHP QEMU bootstrap graph.
#
# This file is intentionally usable before Python, GNU sed, Automake, or the
# managed LLVM fork exists. It selects a compiler that can build *and run*
# native build-machine executables. Target/cross CC and CXX are deliberately
# not consulted; use WHP_CC_SEED/WHP_CXX_SEED or CC_FOR_BUILD/CXX_FOR_BUILD.

set -eu

WHP_CC_ADAPTER_MARKER=whp-qemu-cc-seed-adapter

if [ "${1:-}" = --whp-cc-adapter-probe ]; then
    printf '%s\n' "$WHP_CC_ADAPTER_MARKER"
    exit 0
fi

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-cc-adapter-probe 2>/dev/null || true)
    [ "$marker" = "$WHP_CC_ADAPTER_MARKER" ]
}

resolve_executable()
{
    value=$1
    [ -n "$value" ] || return 1
    if [ -x "$value" ]; then
        # An explicit executable path may legitimately contain whitespace.
        candidate=$value
    else
        # Command names cannot safely contain shell whitespace in this seed
        # interface; callers with such a path should provide the path itself.
        case "$value" in
            *[[:space:]]*) return 1 ;;
        esac
        candidate=$(command -v "$value" 2>/dev/null || true)
    fi
    [ -n "$candidate" ] && [ -x "$candidate" ] || return 1
    is_self "$candidate" && return 1
    "$candidate" --version >/dev/null 2>&1 || return 1
    printf '%s\n' "$candidate"
}

compiler_runs_native()
{
    language=$1
    compiler=$2
    tmp_dir=${TMPDIR:-/tmp}/whp-cc-seed.$$
    rm -rf "$tmp_dir"
    (umask 077 && mkdir "$tmp_dir") || return 1

    case "$language" in
        c)
            src=$tmp_dir/probe.c
            printf '%s\n' 'int main(void) { return 0; }' > "$src"
            if "$compiler" "$src" -o "$tmp_dir/probe" >/dev/null 2>&1 &&
               "$tmp_dir/probe" >/dev/null 2>&1; then
                rm -rf "$tmp_dir"
                return 0
            fi
            ;;
        c++)
            src=$tmp_dir/probe.cc
            printf '%s\n' 'int main() { return 0; }' > "$src"
            if "$compiler" -std=c++17 "$src" -o "$tmp_dir/probe" >/dev/null 2>&1 &&
               "$tmp_dir/probe" >/dev/null 2>&1; then
                rm -rf "$tmp_dir"
                return 0
            fi
            ;;
    esac

    rm -rf "$tmp_dir"
    return 1
}

try_compiler()
{
    language=$1
    value=$2
    candidate=$(resolve_executable "$value" 2>/dev/null || true)
    [ -n "$candidate" ] || return 1
    compiler_runs_native "$language" "$candidate" || return 1
    printf '%s\n' "$candidate"
}

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
        if compiler=$(try_compiler c++ "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
        printf 'error: requested build C++ compiler is not native/C++17-capable: %s\n' "$value" >&2
        return 1
    done

    if command -v xcrun >/dev/null 2>&1; then
        value=$(xcrun --sdk macosx --find clang++ 2>/dev/null || true)
        if [ -n "$value" ] && compiler=$(try_compiler c++ "$value"); then
            printf '%s\n' "$compiler"
            return 0
        fi
    fi

    cc=$(select_cc) || return 1
    value=$(derived_cxx_candidates "$cc" 2>/dev/null || true)
    if [ -n "$value" ] && compiler=$(try_compiler c++ "$value"); then
        printf '%s\n' "$compiler"
        return 0
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
    --print-cc|--print-seed)
        select_cc
        exit $?
        ;;
    --print-cxx)
        select_cxx
        exit $?
        ;;
    --check)
        compiler=$(select_cc)
        printf 'WHP C compiler seed: %s\n' "$compiler"
        exit 0
        ;;
    --check-cxx)
        compiler=$(select_cxx)
        printf 'WHP C++ compiler seed: %s\n' "$compiler"
        exit 0
        ;;
    --cxx)
        shift
        compiler=$(select_cxx)
        exec "$compiler" "$@"
        ;;
esac

compiler=$(select_cc)
exec "$compiler" "$@"
