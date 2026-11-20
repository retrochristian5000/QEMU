#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Native CMake/Ninja producer selection for standalone firmware LLVM lanes.
# Sourced only by Bash bootstraps after their installed-toolchain cache check.

whp_llvm_select_cmake_ninja()
{
    local requested candidate dir

    # LLVM cannot use itself to bootstrap CMake. Reuse the independent seed
    # contract (including explicit overrides and the minimum CMake version).
    whp_llvm_cmake_cmd="$(/bin/sh "$SOURCE_DIR/seeds/cmake.sh" --print-cmake)" || return 1

    # The public QEMU build selects one Ninja. Standalone firmware calls use
    # the same choice if exported, or the native PATH fallback.
    requested="${NINJA_CMD:-${NINJA:-ninja}}"
    [[ -n "$requested" ]] || {
        printf '%s\n' 'error: LLVM host Ninja selection is empty' >&2
        return 1
    }
    case "$requested" in
        */*) candidate="$requested" ;;
        *)
            case "$requested" in
                *[[:space:]]*)
                    printf 'error: Ninja command must name one executable: %s\n' "$requested" >&2
                    return 1
                    ;;
            esac
            candidate="$(command -v "$requested" 2>/dev/null)" || return 1
            ;;
    esac
    [[ -f "$candidate" && -x "$candidate" ]] || {
        printf 'error: LLVM host Ninja is not executable: %s\n' "$requested" >&2
        return 1
    }
    case "$candidate" in
        /*) ;;
        */*)
            dir="$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)" || return 1
            candidate="$dir/${candidate##*/}"
            ;;
        *)
            printf 'error: Ninja selection did not resolve to a path: %s\n' "$candidate" >&2
            return 1
            ;;
    esac
    "$candidate" --version >/dev/null 2>&1 || {
        printf 'error: selected Ninja does not report a version: %s\n' "$candidate" >&2
        return 1
    }
    whp_llvm_ninja_cmd="$candidate"
    printf 'WHP firmware LLVM build tools: cmake=%s; ninja=%s\n' \
        "$whp_llvm_cmake_cmd" "$whp_llvm_ninja_cmd" >&2
}

# CMake's Ninja generator stores CMAKE_MAKE_PROGRAM in the build cache.
# Changing it after generator initialization is unsupported: reject an
# incompatible tool handoff before CMake touches the existing object graph.
whp_llvm_verify_ninja_cache()
{
    local build_dir="$1" cache_file cache_line cached_ninja
    cache_file="$build_dir/CMakeCache.txt"
    [[ -f "$cache_file" ]] || return 0
    cache_line="$(grep '^CMAKE_MAKE_PROGRAM:' "$cache_file" || true)"
    [[ -n "$cache_line" ]] || return 0
    case "$cache_line" in
        *$'\n'*)
            printf 'error: multiple CMAKE_MAKE_PROGRAM entries in %s\n' "$cache_file" >&2
            return 1
            ;;
    esac
    cached_ninja="${cache_line#*=}"
    if [[ "$cached_ninja" != "$whp_llvm_ninja_cmd" ]]; then
        printf '%s\n' \
            'error: existing LLVM Ninja graph was generated with a different build tool.' \
            "cached:   $cached_ninja" \
            "selected: $whp_llvm_ninja_cmd" \
            'Select the cached Ninja or choose a separate LLVM work directory; existing objects were preserved.' >&2
        return 1
    fi
}
