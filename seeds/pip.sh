#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Resolve pip through the selected Python, never a PATH pip executable.
set -eu

case "${1:-}" in
    --whp-pip-adapter-probe)
        printf '%s\n' whp-qemu-pip-seed-adapter
        exit 0 ;;
    --whp-python-adapter-probe)
        # The Python seed must reject this adapter as an interpreter.
        printf '%s\n' whp-qemu-python-seed-adapter
        exit 0 ;;
esac

case "$0" in
    */*) seed_dir=${0%/*}; [ -n "$seed_dir" ] || seed_dir=/ ;;
    *) seed_dir=. ;;
esac
seed_dir=$(CDPATH= cd -P -- "$seed_dir" && pwd -P)

if [ "${1:-}" = --python ]; then
    if [ "$#" -lt 2 ] || [ -z "$2" ]; then
        printf '%s\n' 'error: --python requires an interpreter path' >&2
        exit 2
    fi
    selected=$2
    shift 2
else
    selected=${PYTHON:-${WHP_PYTHON_SEED:-}}
    if [ -z "$selected" ]; then
        selected=$(/bin/sh "$seed_dir/python.sh" --print-seed) || exit 1
    fi
fi

case "$selected" in
    */*) ;;
    *) selected=$(command -v "$selected" 2>/dev/null) || {
        printf '%s\n' 'error: selected Python executable was not found' >&2
        exit 1
    } ;;
esac
case "$selected" in
    /*) ;;
    */*) selected=$(CDPATH= cd -P -- "${selected%/*}" && pwd -P)/${selected##*/} ;;
    *) printf '%s\n' 'error: selected Python must be an executable file' >&2; exit 1 ;;
esac

# Do not resolve the executable symlink: a venv relies on its own path.
# Check the actual interpreter and reject recursive adapter aliases.
if [ ! -f "$selected" ] || [ ! -x "$selected" ] ||
   [ "$("$selected" --whp-python-adapter-probe 2>/dev/null || true)" = whp-qemu-python-seed-adapter ]; then
    printf 'error: pip requires a usable Python >= 3.9: %s\n' "$selected" >&2
    exit 1
fi
if ! identity=$("$selected" -I -B -c '
import sys
if sys.version_info < (3, 9):
    raise SystemExit(1)
print("whp-pip-python-ok")
' 2>/dev/null) || [ "$identity" != whp-pip-python-ok ]; then
    printf 'error: pip requires a usable Python >= 3.9: %s\n' "$selected" >&2
    exit 1
fi

# Isolated mode excludes PYTHONPATH and the user site. No package is
# installed or downloaded by this probe, including pip itself.
if ! version=$("$selected" -I -B -m pip --version); then
    printf 'error: pip unavailable for %s; use the existing managed Python or venv bootstrap\n' "$selected" >&2
    exit 1
fi
case "$version" in
    pip\ *) ;;
    *) printf 'error: invalid pip version response from %s\n' "$selected" >&2; exit 1 ;;
esac

case "${1:-}" in
    --check) printf 'WHP pip seed: %s (%s)\n' "$selected" "$version" ;;
    --print-python) printf '%s\n' "$selected" ;;
    *) exec "$selected" -I -B -m pip "$@" ;;
esac
