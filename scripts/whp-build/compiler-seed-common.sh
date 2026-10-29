#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Shared native compiler probes; sourced only by compiler adapters.

is_self()
{
    candidate=$1
    marker=$("$candidate" --whp-cc-adapter-probe 2>/dev/null || true)
    case "$marker" in
        whp-qemu-cc-seed-adapter|whp-qemu-cxx-seed-adapter) return 0 ;;
    esac
    return 1
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

