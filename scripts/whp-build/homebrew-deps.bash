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

whp_refresh_homebrew_dependency_identity()
{
    local brew_cmd
    local signature
    local manifest
    local candidate
    local config_file
    local config_new

    [[ "${HOST_OS:-$(uname -s)}" == Darwin ]] || return 0

    brew_cmd="$(whp_homebrew_brew_command)"
    [[ -n "$brew_cmd" && -x "$brew_cmd" ]] || return 0
    signature="$(whp_homebrew_dependency_signature "$brew_cmd")" || return 0
    [[ -n "$signature" ]] || return 0

    mkdir -p "$BUILD_DIR"
    manifest="$BUILD_DIR/.whp-homebrew-deps"
    candidate="$manifest.new"
    config_file="$BUILD_DIR/.whp-config"
    config_new="$config_file.homebrew-new"

    {
        printf 'SCHEMA=2\n'
        printf 'SIGNATURE=%s\n' "$signature"
        printf 'BREW=%s\n' "$brew_cmd"
        whp_homebrew_dependency_inventory "$brew_cmd" | sed 's/^/FORMULA=/'
    } > "$candidate"

    if [[ -f "$manifest" ]] && cmp -s "$candidate" "$manifest"; then
        rm -f "$candidate"
        return 0
    fi

    # A persistent tree may predate this manifest, so the first run must also
    # invalidate stale Meson paths. Preserve .whp-config and its target history;
    # the unknown one-shot line forces a single in-place configure refresh.
    if [[ -f "$config_file" && -f "$BUILD_DIR/build.ninja" ]]; then
        awk '!/^WHP_HOMEBREW_DEPENDENCIES_STALE=/' "$config_file" > "$config_new"
        printf 'WHP_HOMEBREW_DEPENDENCIES_STALE=%s\n' "$signature" >> "$config_new"
        mv "$config_new" "$config_file"
        printf '%s\n' \
            'Homebrew dependency paths changed; QEMU will reconfigure in place.'
    fi

    mv "$candidate" "$manifest"
}
