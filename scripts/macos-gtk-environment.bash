#!/usr/bin/env bash

# Source this file after whp_prepare_build.  It repairs the parent build
# environment; executing it in a child process would lose the exports before
# QEMU's configure and Meson stages run.

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
    printf 'error: scripts/macos-gtk-environment.bash must be sourced\n' >&2
    exit 2
fi

if [[ "${HOST_OS:-$(uname -s)}" != Darwin || "${MACOS_ENABLE_GTK:-0}" != 1 ]]; then
    return 0
fi

whp_gtk_append_flag()
{
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"

    case " $current " in
        *" $value "*) return 0 ;;
    esac
    if [[ -n "$current" ]]; then
        printf -v "$variable" '%s %s' "$current" "$value"
    else
        printf -v "$variable" '%s' "$value"
    fi
    export "$variable"
}

whp_gtk_prepend_path()
{
    local variable="$1"
    local value="$2"
    local current="${!variable:-}"

    [[ -d "$value" ]] || return 0
    case ":$current:" in
        *":$value:"*) return 0 ;;
    esac
    if [[ -n "$current" ]]; then
        printf -v "$variable" '%s:%s' "$value" "$current"
    else
        printf -v "$variable" '%s' "$value"
    fi
    export "$variable"
}

if [[ -z "${HOMEBREW_PREFIX:-}" || ! -x "$HOMEBREW_PREFIX/bin/brew" ]]; then
    printf '%s\n' \
        'error: GTK was requested, but the active Homebrew prefix is unavailable.' \
        "HOMEBREW_PREFIX=${HOMEBREW_PREFIX:-<unset>}" >&2
    return 1
fi

brew_cmd="$HOMEBREW_PREFIX/bin/brew"
active_brew_prefix="$("$brew_cmd" --prefix)"
if [[ "$active_brew_prefix" != "$HOMEBREW_PREFIX" ]]; then
    printf '%s\n' \
        'error: Homebrew prefix changed while preparing GTK.' \
        "HOMEBREW_PREFIX=$HOMEBREW_PREFIX" \
        "brew --prefix=$active_brew_prefix" >&2
    return 1
fi

gtk_prefix="$("$brew_cmd" --prefix gtk+3 2>/dev/null || true)"
atk_prefix="$("$brew_cmd" --prefix at-spi2-core 2>/dev/null || true)"
pkgconf_prefix="$("$brew_cmd" --prefix pkgconf 2>/dev/null || true)"

if [[ -z "$gtk_prefix" || ! -d "$gtk_prefix" ]]; then
    printf '%s\n' \
        'error: Homebrew gtk+3 is not installed in the active prefix.' \
        'repair command: brew reinstall gtk+3' >&2
    return 1
fi
if [[ -z "$atk_prefix" || ! -d "$atk_prefix" ]]; then
    printf '%s\n' \
        'error: Homebrew at-spi2-core, the current ATK provider, is not installed.' \
        'repair command: brew reinstall at-spi2-core' >&2
    return 1
fi
if [[ -z "$pkgconf_prefix" || ! -d "$pkgconf_prefix" ]]; then
    printf '%s\n' \
        'error: Homebrew pkgconf is not installed.' \
        'repair command: brew reinstall pkgconf' >&2
    return 1
fi

pkg_config_executable=""
for candidate in \
    "$pkgconf_prefix/bin/pkg-config" \
    "$pkgconf_prefix/bin/pkgconf" \
    "$HOMEBREW_PREFIX/bin/pkg-config"; do
    if [[ -x "$candidate" ]]; then
        pkg_config_executable="$candidate"
        break
    fi
done
if [[ -z "$pkg_config_executable" ]]; then
    printf 'error: no executable Homebrew pkg-config was found under %s\n' \
        "$pkgconf_prefix" >&2
    return 1
fi

# Homebrew normally links .pc files into the prefix, but old macOS source
# builds and formula upgrades can leave only keg-local metadata.  Add gtk+3,
# its full dependency closure, and the canonical prefix directories.
formulae=(gtk+3 at-spi2-core pkgconf)
while IFS= read -r formula; do
    [[ -n "$formula" ]] && formulae+=("$formula")
done < <("$brew_cmd" deps --formula gtk+3 2>/dev/null || true)

for formula in "${formulae[@]}"; do
    formula_prefix="$("$brew_cmd" --prefix "$formula" 2>/dev/null || true)"
    [[ -n "$formula_prefix" && -d "$formula_prefix" ]] || continue
    whp_gtk_prepend_path PKG_CONFIG_PATH "$formula_prefix/share/pkgconfig"
    whp_gtk_prepend_path PKG_CONFIG_PATH "$formula_prefix/lib/pkgconfig"
done
whp_gtk_prepend_path PKG_CONFIG_PATH "$HOMEBREW_PREFIX/share/pkgconfig"
whp_gtk_prepend_path PKG_CONFIG_PATH "$HOMEBREW_PREFIX/lib/pkgconfig"

export PKG_CONFIG="$pkg_config_executable"
export PKG_CONFIG_FOR_BUILD="$pkg_config_executable"
export PKG_CONFIG_PATH_FOR_BUILD="$PKG_CONFIG_PATH"

if ! "$pkg_config_executable" --exists gtk+-3.0; then
    printf '%s\n' \
        'error: gtk+3 is installed, but gtk+-3.0.pc is not resolvable.' \
        "PKG_CONFIG=$pkg_config_executable" \
        "PKG_CONFIG_PATH=$PKG_CONFIG_PATH" >&2
    "$pkg_config_executable" --print-errors --exists gtk+-3.0 2>&1 || true
    return 1
fi
if ! "$pkg_config_executable" --exists atk; then
    printf '%s\n' \
        'error: at-spi2-core is installed, but atk.pc is not resolvable.' \
        "ATK provider=$atk_prefix" \
        "PKG_CONFIG_PATH=$PKG_CONFIG_PATH" >&2
    "$pkg_config_executable" --print-errors --exists atk 2>&1 || true
    return 1
fi

atk_includedir="$("$pkg_config_executable" --variable=includedir atk)"
atk_header="$atk_includedir/atk/atk.h"
if [[ ! -f "$atk_header" ]]; then
    atk_header="$(find "$atk_prefix" -type f -path '*/atk/atk.h' -print -quit 2>/dev/null || true)"
    if [[ -n "$atk_header" ]]; then
        atk_includedir="${atk_header%/atk/atk.h}"
    fi
fi
if [[ -z "$atk_header" || ! -f "$atk_header" ]]; then
    printf '%s\n' \
        'error: Homebrew ATK metadata exists, but atk/atk.h is absent.' \
        "ATK provider=$atk_prefix" \
        'repair command: brew reinstall at-spi2-core' >&2
    return 1
fi

gtk_cflags="$("$pkg_config_executable" --cflags gtk+-3.0)"
case " $gtk_cflags " in
    *" -I$atk_includedir "*) atk_fallback=not-needed ;;
    *)
        # This repairs the exact gtk/gtkwidget.h -> atk/atk.h failure without
        # exposing Homebrew flags to the separately isolated OpenBIOS build.
        whp_gtk_append_flag CPPFLAGS "-I$atk_includedir"
        atk_fallback=enabled
        ;;
esac

printf '%s\n' \
    "GTK Homebrew environment: $gtk_prefix" \
    "ATK Homebrew provider:    $atk_prefix" \
    "ATK header:               $atk_header" \
    "pkg-config:               $pkg_config_executable" \
    "ATK include fallback:     $atk_fallback"
