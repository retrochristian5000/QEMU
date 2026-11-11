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

# A symlinked seed launcher still belongs to this checkout. Resolve its
# physical location before asking the companion Cargo adapter for its seed.
# Do not discover a different cargo.sh beside a PATH alias.
cargo_adapter_path()
(
    entry=$0
    case "$entry" in
        */*) ;;
        *) entry=$(command -v "$entry" 2>/dev/null) || exit 1 ;;
    esac
    depth=0
    while [ -L "$entry" ]; do
        depth=$((depth + 1))
        [ "$depth" -le 16 ] || {
            printf '%s\n' 'error: rustc seed symlink loop' >&2
            exit 1
        }
        link=$(readlink "$entry") || exit 1
        case "$link" in
            /*) entry=$link ;;
            *) entry=${entry%/*}/$link ;;
        esac
    done
    directory=$(CDPATH= cd -P -- "${entry%/*}" && pwd -P) || exit 1
    [ -f "$directory/cargo.sh" ] || {
        printf 'error: companion Cargo seed is missing: %s\n' "$directory/cargo.sh" >&2
        exit 1
    }
    printf '%s\n' "$directory/cargo.sh"
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
    cargo_adapter=$(cargo_adapter_path) || return 1
    # If Cargo is explicitly pinned, prefer the neighboring rustc. A rustup
    # Cargo shim normally has a matching rustc shim in the same directory.
    if [ -n "${WHP_CARGO_SEED:-}" ]; then
        cargo=$(/bin/sh "$cargo_adapter" --print-seed) || return 1
        candidate=${cargo%/*}/rustc
        if selected=$(resolve_rustc "$candidate"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: pinned Cargo lacks a usable adjacent rustc: %s\n' "$candidate" >&2
        return 1
    fi
    # Prefer the same Rust installation as the Cargo found by cargo.sh.
    if cargo=$(/bin/sh "$cargo_adapter" --print-seed 2>/dev/null); then
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
