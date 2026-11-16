#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Independent installed-Python seed; never builds its own interpreter.
set -eu
marker=whp-qemu-python-seed-adapter
if [ "${1:-}" = --whp-python-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

python_resolve()
(
    requested=$1
    [ -n "$requested" ] || exit 1
    case "$requested" in
        *[[:space:]]*) exit 1 ;;
        */*) candidate=$requested ;;
        *) candidate=$(command -v "$requested" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    # Version banners alone and recursive adapter symlinks are insufficient.
    identity=$("$candidate" --whp-python-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    result=$("$candidate" -I -c '
import sys
if sys.version_info < (3, 9):
    raise SystemExit(1)
import pathlib
import venv
print("whp-qemu-host-python-ok")
' 2>/dev/null) || exit 1
    [ "$result" = whp-qemu-host-python-ok ] || exit 1
    printf '%s\n' "$candidate"
)

python_select()
{
    # Explicit choices are authoritative; no silent fallback on failure.
    for variable in PYTHON WHP_PYTHON_SEED; do
        case "$variable" in
            PYTHON) requested=${PYTHON:-} ;;
            WHP_PYTHON_SEED) requested=${WHP_PYTHON_SEED:-} ;;
        esac
        [ -n "$requested" ] || continue
        if chosen=$(python_resolve "$requested"); then
            printf '%s\n' "$chosen"
            return 0
        fi
        printf 'error: %s must select native Python >= 3.9: %s\n' \
            "$variable" "$requested" >&2
        return 1
    done

    # Preserve the public pre-Python macOS Homebrew preference without
    # changing PATH or requiring Homebrew to exist.
    case "${WHP_HOST_OS:-}" in
        macos) host_os=macos ;;
        windows) host_os=windows ;;
        "") case "$(uname -s 2>/dev/null || true)" in
            Darwin) host_os=macos ;;
            MINGW*|MSYS*|CYGWIN*) host_os=windows ;;
            *) host_os=other ;;
        esac ;;
        *) host_os=other ;;
    esac
    if [ "$host_os" = macos ]; then
        host_arch=${WHP_HOST_ARCH:-$(uname -m 2>/dev/null || true)}
        case "$host_arch" in
            arm64|aarch64) brew_prefix=/opt/homebrew ;;
            x86_64) brew_prefix=/usr/local ;;
            *) brew_prefix= ;;
        esac
        if [ -n "$brew_prefix" ]; then
            for requested in \
                "$brew_prefix/bin/python3" \
                "$brew_prefix/opt/python@3.14/bin/python3.14" \
                "$brew_prefix/opt/python@3.13/bin/python3.13" \
                "$brew_prefix/opt/python@3.12/bin/python3.12"; do
                if chosen=$(python_resolve "$requested"); then
                    printf '%s\n' "$chosen"
                    return 0
                fi
            done
        fi
    fi

    for requested in python3 python; do
        if chosen=$(python_resolve "$requested"); then
            printf '%s\n' "$chosen"
            return 0
        fi
    done

    # Windows py is only a locator, not the interpreter passed downstream.
    if [ "$host_os" = windows ]; then
        launcher=$(command -v py 2>/dev/null || true)
        if [ -n "$launcher" ]; then
            requested=$("$launcher" -c 'import sys; print(sys.executable)' \
                2>/dev/null || true)
            if chosen=$(python_resolve "$requested"); then
                printf '%s\n' "$chosen"
                return 0
            fi
        fi
    fi

    printf '%s\n' 'error: no installed Python >= 3.9; allow the existing bundled Python fallback' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-python) python_select ;;
    --check)
        chosen=$(python_select) || exit 1
        printf 'WHP Python seed: %s (Python >= 3.9, runtime and venv verified)\n' \
            "$chosen" ;;
    *)
        chosen=$(python_select) || exit 1
        exec "$chosen" "$@" ;;
esac
