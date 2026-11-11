#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Select an existing native Cargo for the WHP pre-QEMU Rust bootstrap.
# Cargo is a root tool: it cannot bootstrap the Cargo needed to build sccache.
set -eu

marker=whp-qemu-cargo-seed-adapter
if [ "${1:-}" = --whp-cargo-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_cargo()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in *[[:space:]]*) exit 1 ;; esac
    case "$value" in
        */*) candidate=$value ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    # Avoid a seed calling itself, including through symlinked PATH entries.
    probe=$("$candidate" --whp-cargo-adapter-probe 2>/dev/null || true)
    [ "$probe" != "$marker" ] || exit 1
    version=$("$candidate" --version 2>/dev/null) || exit 1
    case "$version" in
        'cargo '[0-9]* ) ;;
        *) exit 1 ;;
    esac
    dir=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
    printf '%s\n' "$dir/${candidate##*/}"
)

select_cargo()
{
    if [ -n "${WHP_CARGO_SEED:-}" ]; then
        resolve_cargo "$WHP_CARGO_SEED" || {
            printf 'error: WHP_CARGO_SEED is not a usable Cargo: %s\n' "$WHP_CARGO_SEED" >&2
            return 1
        }
        return 0
    fi
    # A Rustup-managed cargo shim is valid; do not force Homebrew Cargo.
    # Prefer explicit PATH before looking in the conventional rustup home.
    path_cargo=$(command -v cargo 2>/dev/null || true)
    if [ -n "$path_cargo" ]; then
        if selected=$(resolve_cargo "$path_cargo"); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    cargo_home=${CARGO_HOME:-${HOME:-}/.cargo}
    if [ -n "$cargo_home" ] && [ -x "$cargo_home/bin/cargo" ]; then
        if selected=$(resolve_cargo "$cargo_home/bin/cargo"); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    printf '%s\n' 'error: no usable host Cargo found for WHP Rust bootstrap' >&2
    return 1
}

case "${1:-}" in
    --print-seed) select_cargo; exit $? ;;
    --check)
        selected=$(select_cargo) || exit 1
        printf 'WHP Cargo seed: %s\n' "$selected"
        exit 0 ;;
esac

selected=$(select_cargo) || exit 1
exec "$selected" "$@"
