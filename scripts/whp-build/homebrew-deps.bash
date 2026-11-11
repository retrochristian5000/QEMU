# Homebrew dependency identity for persistent macOS QEMU build trees.
# SPDX-License-Identifier: GPL-2.0-or-later
# Keep this compatible with the Bash 3.2 shipped by macOS.

whp_homebrew_brew_command()
{
    if [[ -n "${WHP_HOMEBREW_BREW:-}" && -x "$WHP_HOMEBREW_BREW" ]]; then
        printf '%s\n' "$WHP_HOMEBREW_BREW"
        return 0
    fi
    if [[ -n "${HOMEBREW_PREFIX:-}" && -x "$HOMEBREW_PREFIX/bin/brew" ]]; then
        printf '%s\n' "$HOMEBREW_PREFIX/bin/brew"
        return 0
    fi
    command -v brew 2>/dev/null || true
}

whp_homebrew_dependency_inventory()
{
    local brew_cmd="$1"

    [[ -x "$brew_cmd" ]] || return 1
    "$brew_cmd" list --formula --versions 2>/dev/null | LC_ALL=C sort
}

whp_homebrew_dependency_signature()
{
    local brew_cmd="$1"
    local inventory

    inventory="$(whp_homebrew_dependency_inventory "$brew_cmd")" || return 1
    printf '%s\n' "$inventory" | cksum | awk '{ printf "%s:%s\n", $1, $2 }'
}

whp_prepare_homebrew_pkg_config()
{
    local wrapper="$SOURCE_DIR/scripts/whp-build/pkg-config-homebrew.bash"
    local real_pkg_config="${PKG_CONFIG:-pkg-config}"

    [[ "${HOST_OS:-$(uname -s)}" == Darwin ]] || return 0
    [[ "${WHP_MACOS_DEPENDENCY_PROVIDER:-homebrew}" == homebrew ]] || return 0
    [[ -x "$wrapper" ]] || {
        printf 'error: Homebrew pkg-config wrapper is missing: %s\n' "$wrapper" >&2
        return 1
    }

    if [[ "$real_pkg_config" != "$wrapper" ]]; then
        WHP_REAL_PKG_CONFIG="$real_pkg_config"
        export WHP_REAL_PKG_CONFIG
    fi
    PKG_CONFIG="$wrapper"
    PKG_CONFIG_FOR_BUILD="$wrapper"
    export PKG_CONFIG PKG_CONFIG_FOR_BUILD
}

# MacPorts installs use stable paths, but Meson's dependency and version
# results must be refreshed after an active-port upgrade.
whp_macports_port_command()
{
    if [[ -n "${WHP_MACPORTS_PORT:-}" && -x "$WHP_MACPORTS_PORT" ]]; then
        printf '%s\n' "$WHP_MACPORTS_PORT"
    elif [[ -x "${MACPORTS_PREFIX:-/opt/local}/bin/port" ]]; then
        printf '%s\n' "${MACPORTS_PREFIX:-/opt/local}/bin/port"
    fi
}

whp_macports_dependency_inventory()
{
    local port_cmd="$1"
    [[ -x "$port_cmd" ]] || return 1
    "$port_cmd" -q installed 2>/dev/null | LC_ALL=C sort
}

whp_macports_dependency_signature()
{
    local inventory
    inventory="$(whp_macports_dependency_inventory "$1")" || return 1
    printf '%s\n' "$inventory" | cksum | awk '{ printf "%s:%s\n", $1, $2 }'
}

# The existing Homebrew manifest and stale-key names remain compatible with
# old build trees. MacPorts shares the same non-destructive refresh mechanism.
whp_refresh_macos_dependency_identity()
{
    local provider="${WHP_MACOS_DEPENDENCY_PROVIDER:-homebrew}"
    local manager inventory signature manifest candidate config_file config_new
    local stale_key manager_key item_key

    [[ "${HOST_OS:-$(uname -s)}" == Darwin ]] || return 0
    case "$provider" in
        homebrew)
            manager="$(whp_homebrew_brew_command)"
            [[ -n "$manager" && -x "$manager" ]] || return 0
            inventory="$(whp_homebrew_dependency_inventory "$manager")" || return 0
            manifest="$BUILD_DIR/.whp-homebrew-deps"
            stale_key=WHP_HOMEBREW_DEPENDENCIES_STALE
            manager_key=BREW
            item_key=FORMULA
            ;;
        macports)
            manager="$(whp_macports_port_command)"
            if [[ -z "$manager" || ! -x "$manager" ]]; then
                printf 'error: MacPorts inventory tool is unavailable\n' >&2
                return 1
            fi
            inventory="$(whp_macports_dependency_inventory "$manager")" || {
                printf 'error: unable to list installed MacPorts dependencies\n' >&2
                return 1
            }
            manifest="$BUILD_DIR/.whp-macports-deps"
            stale_key=WHP_MACPORTS_DEPENDENCIES_STALE
            manager_key=PORT
            item_key=PACKAGE
            ;;
        system) return 0 ;;
        *) printf 'error: unknown macOS dependency provider: %s\n' "$provider" >&2; return 1 ;;
    esac
    signature="$(printf '%s\n' "$inventory" | cksum | awk '{ printf "%s:%s\n", $1, $2 }')"
    mkdir -p "$BUILD_DIR"
    candidate="$manifest.new"
    config_file="$BUILD_DIR/.whp-config"
    config_new="$config_file.${provider}-new"

    {
        printf 'SCHEMA=2\n'
        printf 'SIGNATURE=%s\n' "$signature"
        printf '%s=%s\n' "$manager_key" "$manager"
        printf '%s\n' "$inventory" | sed "s/^/$item_key=/"
    } > "$candidate"

    if [[ -f "$manifest" ]] && cmp -s "$candidate" "$manifest"; then
        rm -f "$candidate"
        return 0
    fi

    # Preserve existing outputs and force exactly one configure refresh.
    if [[ -f "$config_file" && -f "$BUILD_DIR/build.ninja" ]]; then
        awk -v key="$stale_key" '$0 !~ "^" key "=" { print }' \
            "$config_file" > "$config_new"
        printf '%s=%s\n' "$stale_key" "$signature" >> "$config_new"
        mv "$config_new" "$config_file"
        printf '%s dependencies changed; QEMU will reconfigure in place.\n' "$provider"
    fi
    mv "$candidate" "$manifest"
}

whp_refresh_homebrew_dependency_identity()
{
    local WHP_MACOS_DEPENDENCY_PROVIDER=homebrew
    whp_refresh_macos_dependency_identity
}
