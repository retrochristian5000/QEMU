#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native rustc seed for the WHP pre-QEMU Cargo/sccacher bootstrap.
# Rustup shims are valid; never try to bootstrap rustc with rustc itself.
set -eu

marker=whp-qemu-rustc-seed-adapter
if [ "${1:-}" = --whp-rustc-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_rustc()
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
        */*)
            directory=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P) || exit 1
            candidate=$directory/${candidate##*/}
            ;;
        *) exit 1 ;;
    esac
    # Adapter marker works even for a copy or symlink placed on PATH.
    probe=$("$candidate" --whp-rustc-adapter-probe 2>/dev/null || true)
    [ "$probe" != "$marker" ] || exit 1
    version=$("$candidate" --version 2>/dev/null) || exit 1
    case "$version" in
        'rustc '[0-9]*.*.*) ;;
        *) exit 1 ;;
    esac
    printf '%s\n' "$candidate"
)

select_rustc()
{
    if [ -n "${WHP_RUSTC_SEED:-}" ]; then
        resolve_rustc "$WHP_RUSTC_SEED" || {
            printf 'error: WHP_RUSTC_SEED is not a usable rustc: %s\n' "$WHP_RUSTC_SEED" >&2
            return 1
        }
        return 0
    fi
    # If Cargo is explicitly pinned, prefer the neighboring rustc. A rustup
    # Cargo shim normally has a matching rustc shim in the same directory.
    if [ -n "${WHP_CARGO_SEED:-}" ]; then
        cargo=$(/bin/sh "${0%/*}/cargo.sh" --print-seed) || return 1
        candidate=${cargo%/*}/rustc
        if selected=$(resolve_rustc "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: pinned Cargo lacks a usable adjacent rustc: %s\n' "$candidate" >&2
        return 1
    fi
    # Prefer the same Rust installation as the Cargo found by cargo.sh.
    if cargo=$(/bin/sh "${0%/*}/cargo.sh" --print-seed 2>/dev/null); then
        if selected=$(resolve_rustc "${cargo%/*}/rustc"); then
            printf '%s\n' "$selected"
            return 0
        fi
    fi
    for value in rustc "${CARGO_HOME:-${HOME:-}/.cargo}/bin/rustc"; do
        if selected=$(resolve_rustc "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    # Homebrew might be absent from PATH at this early bootstrap stage.
    if [ "$(uname -s 2>/dev/null || true)" = Darwin ]; then
        case "$(uname -m 2>/dev/null || true)" in
            arm64|aarch64) brew=/opt/homebrew ;;
            x86_64) brew=/usr/local ;;
            *) brew= ;;
        esac
        if [ -n "$brew" ]; then
            for value in "$brew/bin/rustc" "$brew/opt/rust/bin/rustc"; do
                if selected=$(resolve_rustc "$value"); then
                    printf '%s\n' "$selected"
                    return 0
                fi
            done
        fi
    fi
    printf '%s\n' 'error: no usable host rustc found for WHP Rust bootstrap' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-rustc) select_rustc ;;
    --check)
        selected=$(select_rustc) || exit 1
        printf 'WHP rustc seed: %s\n' "$selected" ;;
    *)
        selected=$(select_rustc) || exit 1
        exec "$selected" "$@" ;;
esac
