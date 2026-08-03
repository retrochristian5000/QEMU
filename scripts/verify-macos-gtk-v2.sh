#!/usr/bin/env bash

set -euo pipefail

if [[ "$(uname -s)" != "Darwin" || "${MACOS_ENABLE_GTK:-0}" != "1" ]]; then
    exit 0
fi

: "${BUILD_DIR:?BUILD_DIR is required}"

split_command()
{
    local value="$1"
    local output_name="$2"

    case "$value" in
        ''|*';'*|*'|'*|*'&'*|*'<'*|*'>') return 1 ;;
    esac
    eval "$output_name=()"
    eval "read -r -a $output_name <<< \"\$value\""
    eval "[[ \${#$output_name[@]} -gt 0 ]]"
}

find_brew_formula()
{
    local candidate
    local prefix

    for candidate in "$@"; do
        if prefix="$("${brew_cmd[@]}" --prefix "$candidate" 2>/dev/null)" &&
           [[ -d "$prefix" ]]; then
            printf '%s|%s\n' "$candidate" "$prefix"
            return 0
        fi
    done
    return 1
}

physical_directory()
{
    local directory="$1"
    (cd -- "$directory" && pwd -P)
}

pkg_config_value="${PKG_CONFIG:-pkg-config}"
cc_value="${CC:-cc}"
pkg_config_cmd=()
cc_cmd=()
brew_cmd=()

if ! split_command "$pkg_config_value" pkg_config_cmd ||
   ! command -v "${pkg_config_cmd[0]}" >/dev/null 2>&1; then
    printf 'error: GTK verification cannot run pkg-config: %s\n' \
        "$pkg_config_value" >&2
    exit 1
fi
if ! split_command "$cc_value" cc_cmd ||
   ! command -v "${cc_cmd[0]}" >/dev/null 2>&1; then
    printf 'error: GTK verification cannot run the host compiler: %s\n' \
        "$cc_value" >&2
    exit 1
fi

if ! "${pkg_config_cmd[@]}" --atleast-version=3.22.0 gtk+-3.0; then
    printf '%s\n' \
        'error: MACOS_ENABLE_GTK=1 requires gtk+-3.0 >= 3.22.0.' \
        "pkg-config: $pkg_config_value" \
        "PKG_CONFIG_PATH=${PKG_CONFIG_PATH:-}" >&2
    "${pkg_config_cmd[@]}" --print-errors --exists 'gtk+-3.0 >= 3.22.0' \
        2>&1 || true
    exit 1
fi
if ! "${pkg_config_cmd[@]}" --exists atk; then
    printf '%s\n' \
        'error: GTK 3 was found, but its ATK dependency metadata is missing.' \
        'Current Homebrew provides atk.pc through the at-spi2-core formula.' \
        "pkg-config: $pkg_config_value" \
        "PKG_CONFIG_PATH=${PKG_CONFIG_PATH:-}" >&2
    "${pkg_config_cmd[@]}" --print-errors --exists atk 2>&1 || true
    exit 1
fi

gtk_cflags="$("${pkg_config_cmd[@]}" --cflags gtk+-3.0)"
atk_cflags="$("${pkg_config_cmd[@]}" --cflags atk)"
gtk_libs="$("${pkg_config_cmd[@]}" --libs gtk+-3.0)"
gtk_version="$("${pkg_config_cmd[@]}" --modversion gtk+-3.0)"
atk_version="$("${pkg_config_cmd[@]}" --modversion atk)"
gtk_pcfiledir="$("${pkg_config_cmd[@]}" --variable=pcfiledir gtk+-3.0)"
atk_pcfiledir="$("${pkg_config_cmd[@]}" --variable=pcfiledir atk)"
atk_includedir="$("${pkg_config_cmd[@]}" --variable=includedir atk)"
gtk_libdir="$("${pkg_config_cmd[@]}" --variable=libdir gtk+-3.0)"
atk_libdir="$("${pkg_config_cmd[@]}" --variable=libdir atk)"
pkg_config_version="$("${pkg_config_cmd[@]}" --version 2>&1 | sed -n '1p')"
pkg_config_executable="$(command -v "${pkg_config_cmd[0]}")"

brew_value="unavailable"
brew_version="unavailable"
brew_prefix="unavailable"
gtk_formula_name="unavailable"
gtk_formula_version="unavailable"
gtk_formula_prefix="unavailable"
gtk_formula_prefix_real="unavailable"
atk_formula_name="unavailable"
atk_formula_version="unavailable"
atk_formula_prefix="unavailable"
atk_formula_prefix_real="unavailable"
pkgconf_formula_name="unavailable"
pkgconf_formula_version="unavailable"
pkgconf_formula_prefix="unavailable"
pkgconf_formula_prefix_real="unavailable"

if [[ -n "${HOMEBREW_PREFIX:-}" && -x "$HOMEBREW_PREFIX/bin/brew" ]]; then
    brew_value="$HOMEBREW_PREFIX/bin/brew"
    brew_cmd=("$brew_value")
    brew_prefix="$("${brew_cmd[@]}" --prefix)"
    brew_version="$("${brew_cmd[@]}" --version 2>&1 | sed -n '1p')"

    if [[ "$brew_prefix" != "$HOMEBREW_PREFIX" ]]; then
        printf '%s\n' \
            'error: Homebrew prefix identity is inconsistent.' \
            "HOMEBREW_PREFIX=$HOMEBREW_PREFIX" \
            "brew --prefix=$brew_prefix" >&2
        exit 1
    fi

    formula_identity="$(find_brew_formula 'gtk+3')" || {
        printf '%s\n' \
            'error: gtk+3 is not installed in the active Homebrew prefix.' \
            "Homebrew prefix: $brew_prefix" \
            'Install or repair it with: brew reinstall gtk+3' >&2
        exit 1
    }
    IFS='|' read -r gtk_formula_name gtk_formula_prefix <<< "$formula_identity"

    formula_identity="$(find_brew_formula 'at-spi2-core' 'atk' 'at-spi2-atk')" || {
        printf '%s\n' \
            'error: the Homebrew provider for ATK is not installed.' \
            "Homebrew prefix: $brew_prefix" \
            'Install or repair it with: brew reinstall at-spi2-core' >&2
        exit 1
    }
    IFS='|' read -r atk_formula_name atk_formula_prefix <<< "$formula_identity"

    formula_identity="$(find_brew_formula 'pkgconf' 'pkg-config')" || {
        printf '%s\n' \
            'error: Homebrew pkgconf is not installed.' \
            "Homebrew prefix: $brew_prefix" \
            'Install or repair it with: brew reinstall pkgconf' >&2
        exit 1
    }
    IFS='|' read -r pkgconf_formula_name pkgconf_formula_prefix <<< "$formula_identity"

    gtk_formula_prefix_real="$(physical_directory "$gtk_formula_prefix")"
    atk_formula_prefix_real="$(physical_directory "$atk_formula_prefix")"
    pkgconf_formula_prefix_real="$(physical_directory "$pkgconf_formula_prefix")"
    gtk_formula_version="$("${brew_cmd[@]}" list --versions "$gtk_formula_name" 2>/dev/null || true)"
    atk_formula_version="$("${brew_cmd[@]}" list --versions "$atk_formula_name" 2>/dev/null || true)"
    pkgconf_formula_version="$("${brew_cmd[@]}" list --versions "$pkgconf_formula_name" 2>/dev/null || true)"

    gtk_pcfiledir_real="$(physical_directory "$gtk_pcfiledir")"
    atk_pcfiledir_real="$(physical_directory "$atk_pcfiledir")"
    atk_includedir_real="$(physical_directory "$atk_includedir")"

    case "$gtk_pcfiledir_real/" in
        "$gtk_formula_prefix_real/"*) ;;
        *)
            printf '%s\n' \
                'error: gtk+-3.0.pc does not belong to the active Homebrew gtk+3 keg.' \
                "gtk+3 keg:  $gtk_formula_prefix_real" \
                "GTK pcfile: $gtk_pcfiledir_real" >&2
            exit 1
            ;;
    esac
    case "$atk_pcfiledir_real/" in
        "$atk_formula_prefix_real/"*) ;;
        *)
            printf '%s\n' \
                'error: atk.pc does not belong to the active Homebrew ATK provider.' \
                "ATK keg:    $atk_formula_prefix_real" \
                "ATK pcfile: $atk_pcfiledir_real" >&2
            exit 1
            ;;
    esac
    case "$atk_includedir_real/" in
        "$atk_formula_prefix_real/"*) ;;
        *)
            printf '%s\n' \
                'error: atk.pc resolves an include directory outside its Homebrew keg.' \
                "ATK keg:     $atk_formula_prefix_real" \
                "ATK include: $atk_includedir_real" >&2
            exit 1
            ;;
    esac
fi

cppflags=()
cflags=()
ldflags=()
gtk_flags=()
gtk_link_flags=()
read -r -a cppflags <<< "${CPPFLAGS:-}"
read -r -a cflags <<< "${CFLAGS:-}"
read -r -a ldflags <<< "${LDFLAGS:-}"
read -r -a gtk_flags <<< "$gtk_cflags"
read -r -a gtk_link_flags <<< "$gtk_libs"

mkdir -p "$BUILD_DIR"
probe_dir="$(mktemp -d "$BUILD_DIR/.whp-gtk-probe.XXXXXX")"
manifest="$BUILD_DIR/.whp-macos-gtk"
candidate="$manifest.new.$$"

cleanup()
{
    rm -rf "$probe_dir"
    rm -f "$candidate"
}
trap cleanup EXIT

cat > "$probe_dir/gtk-header-probe.c" <<'EOF_PROBE'
#include <gtk/gtk.h>

int main(void)
{
    GtkWidget *widget = (GtkWidget *)0;
    AtkObject *accessible = (AtkObject *)0;

    (void)widget;
    (void)accessible;
    gtk_disable_setlocale();
    return gtk_get_major_version() == 3 ? 0 : 1;
}
EOF_PROBE

if ! "${cc_cmd[@]}" "${cppflags[@]}" "${cflags[@]}" \
        "${gtk_flags[@]}" "$probe_dir/gtk-header-probe.c" \
        -o "$probe_dir/gtk-header-probe" \
        "${ldflags[@]}" "${gtk_link_flags[@]}"; then
    printf '%s\n' \
        'error: pkg-config reports GTK 3, but it cannot compile and link.' \
        'The gtk/gtkwidget.h -> atk/atk.h chain or Homebrew libraries are inconsistent.' \
        "GTK version:       $gtk_version" \
        "GTK pcfile:        $gtk_pcfiledir" \
        "GTK library dir:   $gtk_libdir" \
        "ATK version:       $atk_version" \
        "ATK pcfile:        $atk_pcfiledir" \
        "ATK include:       $atk_includedir" \
        "ATK library dir:   $atk_libdir" \
        "pkg-config:        $pkg_config_executable ($pkg_config_version)" \
        "GTK cflags:        $gtk_cflags" \
        "GTK linker flags:  $gtk_libs" >&2
    exit 1
fi

if ! "$probe_dir/gtk-header-probe"; then
    printf '%s\n' \
        'error: the GTK compile-and-link probe produced an unusable executable.' \
        "GTK version: $gtk_version" \
        "Host arch:   ${MACOS_HOST_ARCH:-unknown}" >&2
    exit 1
fi

cc_version="$("${cc_cmd[@]}" --version 2>&1 | sed -n '1p' || true)"
{
    printf 'SCHEMA=2\n'
    printf 'MACOS_HOST_ARCH=%s\n' "${MACOS_HOST_ARCH:-}"
    printf 'CC=%s\n' "$cc_value"
    printf 'CC_VERSION=%s\n' "$cc_version"
    printf 'PKG_CONFIG=%s\n' "$pkg_config_value"
    printf 'PKG_CONFIG_EXECUTABLE=%s\n' "$pkg_config_executable"
    printf 'PKG_CONFIG_VERSION=%s\n' "$pkg_config_version"
    printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
    printf 'BREW=%s\n' "$brew_value"
    printf 'BREW_VERSION=%s\n' "$brew_version"
    printf 'BREW_PREFIX=%s\n' "$brew_prefix"
    printf 'GTK_FORMULA=%s\n' "$gtk_formula_name"
    printf 'GTK_FORMULA_VERSION=%s\n' "$gtk_formula_version"
    printf 'GTK_FORMULA_PREFIX=%s\n' "$gtk_formula_prefix"
    printf 'GTK_FORMULA_PREFIX_REAL=%s\n' "$gtk_formula_prefix_real"
    printf 'ATK_FORMULA=%s\n' "$atk_formula_name"
    printf 'ATK_FORMULA_VERSION=%s\n' "$atk_formula_version"
    printf 'ATK_FORMULA_PREFIX=%s\n' "$atk_formula_prefix"
    printf 'ATK_FORMULA_PREFIX_REAL=%s\n' "$atk_formula_prefix_real"
    printf 'PKGCONF_FORMULA=%s\n' "$pkgconf_formula_name"
    printf 'PKGCONF_FORMULA_VERSION=%s\n' "$pkgconf_formula_version"
    printf 'PKGCONF_FORMULA_PREFIX=%s\n' "$pkgconf_formula_prefix"
    printf 'PKGCONF_FORMULA_PREFIX_REAL=%s\n' "$pkgconf_formula_prefix_real"
    printf 'GTK_VERSION=%s\n' "$gtk_version"
    printf 'GTK_PCFILEDIR=%s\n' "$gtk_pcfiledir"
    printf 'GTK_LIBDIR=%s\n' "$gtk_libdir"
    printf 'GTK_CFLAGS=%s\n' "$gtk_cflags"
    printf 'GTK_LIBS=%s\n' "$gtk_libs"
    printf 'ATK_VERSION=%s\n' "$atk_version"
    printf 'ATK_PCFILEDIR=%s\n' "$atk_pcfiledir"
    printf 'ATK_INCLUDEDIR=%s\n' "$atk_includedir"
    printf 'ATK_LIBDIR=%s\n' "$atk_libdir"
    printf 'ATK_CFLAGS=%s\n' "$atk_cflags"
} > "$candidate"

if [[ ! -f "$manifest" ]] || ! cmp -s "$candidate" "$manifest"; then
    if [[ -f "$BUILD_DIR/build.ninja" ]]; then
        rm -f "$BUILD_DIR/.whp-config"
        printf '%s\n' \
            'GTK/ATK/Homebrew dependency identity changed; forcing QEMU reconfiguration.' \
            "GTK pcfile: $gtk_pcfiledir" \
            "ATK pcfile: $atk_pcfiledir"
    fi
    mv "$candidate" "$manifest"
else
    rm -f "$candidate"
fi

printf '%s\n' \
    "GTK compile/link probe:   usable ($gtk_version)" \
    "GTK pkg-config metadata:  $gtk_pcfiledir" \
    "ATK pkg-config metadata:  $atk_pcfiledir" \
    "pkg-config executable:    $pkg_config_executable ($pkg_config_version)"
if [[ "$brew_prefix" != "unavailable" ]]; then
    printf '%s\n' \
        "Homebrew GTK formula:     $gtk_formula_version" \
        "Homebrew ATK provider:    $atk_formula_version" \
        "Homebrew pkgconf formula: $pkgconf_formula_version"
fi
