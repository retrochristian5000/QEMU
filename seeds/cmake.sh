#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Independent CMake host seed; never bootstraps CMake through LLVM.
set -eu
marker=whp-qemu-cmake-seed-adapter
if [ "${1:-}" = --whp-cmake-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

cmake_resolve()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in *[[:space:]]*) exit 1 ;; esac
    case "$value" in
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-cmake-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    banner=$("$candidate" --version 2>/dev/null) || exit 1
    first=$(printf '%s\n' "$banner" | sed -n '1p')
    case "$first" in
        "cmake version "*) version=${first#cmake version } ;;
        *) exit 1 ;;
    esac
    major=${version%%.*}
    rest=${version#*.}
    [ "$rest" != "$version" ] || exit 1
    minor=${rest%%.*}
    case "$major:$minor" in
        *[!0-9:]*|:*|*:|*::* ) exit 1 ;;
    esac
    [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 20 ]; } || exit 1
    printf '%s\n' "$candidate"
)

cmake_fork_bootstrap()
{
    entry=$0
    case "$entry" in
        */*) ;;
        *) entry=$(command -v "$entry" 2>/dev/null) || return 1 ;;
    esac
    depth=0
    while [ -L "$entry" ]; do
        depth=$((depth + 1))
        [ "$depth" -le 16 ] || {
            printf '%s\n' 'error: CMake seed symlink loop' >&2
            return 1
        }
        link=$(readlink "$entry") || return 1
        case "$link" in
            /*) entry=$link ;;
            *) entry=${entry%/*}/$link ;;
        esac
    done
    root=$(CDPATH= cd -P -- "${entry%/*}/.." && pwd -P) || return 1
    python=${PYTHON:-python3}
    command -v "$python" >/dev/null 2>&1 || {
        printf '%s\n' 'error: pinned CMake bootstrap requires host Python' >&2
        return 1
    }
    built=$("$python" "$root/scripts/ensure-cmake.py" \
        --build-dir "${BUILD_DIR:-$root/build}") || return 1
    cmake_resolve "$built"
}

cmake_select()
{
    case "${BOOTSTRAP_CMAKE:-auto}" in
        auto) policy=auto ;;
        1|y) policy=1 ;;
        0|n) policy=0 ;;
        *)
            printf 'error: invalid BOOTSTRAP_CMAKE: %s\n' "$BOOTSTRAP_CMAKE" >&2
            return 1 ;;
    esac
    if [ "$policy" = 1 ]; then
        if [ -n "${WHP_CMAKE_SEED:-}" ] || [ -n "${CMAKE_CMD:-}" ] || \
           [ -n "${CMAKE:-}" ]; then
            printf '%s\n' 'error: BOOTSTRAP_CMAKE=1 conflicts with an explicit CMake executable' >&2
            return 1
        fi
        cmake_fork_bootstrap
        return $?
    fi
    # Explicit overrides fail closed, never falling back to another program.
    for variable in WHP_CMAKE_SEED CMAKE_CMD CMAKE; do
        case "$variable" in
            WHP_CMAKE_SEED) requested=${WHP_CMAKE_SEED:-} ;;
            CMAKE_CMD) requested=${CMAKE_CMD:-} ;;
            CMAKE) requested=${CMAKE:-} ;;
        esac
        [ -n "$requested" ] || continue
        if selected=$(cmake_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s must select host CMake >= 3.20: %s\n' "$variable" "$requested" >&2
        return 1
    done
    for requested in cmake \
        "${HOMEBREW_PREFIX:-/opt/homebrew}/bin/cmake" \
        /opt/homebrew/bin/cmake /usr/local/bin/cmake; do
        if selected=$(cmake_resolve "$requested"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    if [ "$policy" = auto ]; then
        cmake_fork_bootstrap
        return $?
    fi
    printf '%s\n' 'error: no usable host CMake >= 3.20 (BOOTSTRAP_CMAKE=0)' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-cmake) cmake_select ;;
    --check)
        selected=$(cmake_select) || exit 1
        printf 'WHP CMake seed: %s\n' "$selected" ;;
    *)
        selected=$(cmake_select) || exit 1
        exec "$selected" "$@" ;;
esac
