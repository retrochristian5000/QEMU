#!/bin/sh
# SPDX-License-Identifier: GPL-2.0-or-later
# Native build-machine pkg-config/pkgconf selection; not a package installer.
set -eu

marker=whp-qemu-pkg-config-seed-adapter
if [ "${1:-}" = --whp-pkg-config-adapter-probe ]; then
    printf '%s\n' "$marker"
    exit 0
fi

resolve_pkg_config()
(
    value=$1
    [ -n "$value" ] || exit 1
    case "$value" in
        */*) candidate=$value ;;
        *[[:space:]]*) exit 1 ;;
        *) candidate=$(command -v "$value" 2>/dev/null) || exit 1 ;;
    esac
    [ -f "$candidate" ] && [ -x "$candidate" ] || exit 1
    case "$candidate" in
        /*) ;;
        */*) candidate=$(CDPATH= cd -P -- "${candidate%/*}" && pwd -P)/${candidate##*/} || exit 1 ;;
        *) exit 1 ;;
    esac
    identity=$("$candidate" --whp-pkg-config-adapter-probe 2>/dev/null || true)
    [ "$identity" != "$marker" ] || exit 1
    version=$("$candidate" --version 2>/dev/null) || exit 1
    [ -n "$version" ] || exit 1
    printf '%s\n' "$candidate"
)

select_pkg_config()
{
    # A build-machine override is authoritative, including after MacPorts
    # selects its isolated pkgconf or Homebrew installs an output wrapper.
    for name in WHP_PKG_CONFIG_SEED PKG_CONFIG_FOR_BUILD PKG_CONFIG; do
        case "$name" in
            WHP_PKG_CONFIG_SEED) value=${WHP_PKG_CONFIG_SEED:-} ;;
            PKG_CONFIG_FOR_BUILD) value=${PKG_CONFIG_FOR_BUILD:-} ;;
            PKG_CONFIG) value=${PKG_CONFIG:-} ;;
        esac
        [ -n "$value" ] || continue
        if selected=$(resolve_pkg_config "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
        printf 'error: %s is not a usable pkg-config/pkgconf: %s\n' "$name" "$value" >&2
        return 1
    done

    # The package-manager stage prepends the selected provider's bin directory.
    # Do not use another provider's hard-coded prefix as a fallback.
    for value in pkg-config pkgconf; do
        if selected=$(resolve_pkg_config "$value"); then
            printf '%s\n' "$selected"
            return 0
        fi
    done
    printf '%s\n' 'error: no usable host pkg-config or pkgconf found' >&2
    return 1
}

case "${1:-}" in
    --print-seed|--print-pkg-config)
        select_pkg_config ;;
    --check)
        selected=$(select_pkg_config) || exit 1
        printf 'WHP pkg-config seed: %s\n' "$selected" ;;
    *)
        selected=$(select_pkg_config) || exit 1
        exec "$selected" "$@" ;;
esac
