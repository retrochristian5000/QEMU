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

pkg_config_value="${PKG_CONFIG:-pkg-config}"
cc_value="${CC:-cc}"
pkg_config_cmd=()
cc_cmd=()

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
        'On current Homebrew installations, atk.pc is supplied by at-spi2-core.' \
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

cppflags=()
cflags=()
gtk_flags=()
read -r -a cppflags <<< "${CPPFLAGS:-}"
read -r -a cflags <<< "${CFLAGS:-}"
read -r -a gtk_flags <<< "$gtk_cflags"

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
    AtkObject *accessible = gtk_widget_get_accessible(widget);
    return accessible != (AtkObject *)0;
}
EOF_PROBE

if ! "${cc_cmd[@]}" "${cppflags[@]}" "${cflags[@]}" \
        "${gtk_flags[@]}" -fsyntax-only "$probe_dir/gtk-header-probe.c"; then
    printf '%s\n' \
        'error: pkg-config reports GTK 3, but <gtk/gtk.h> is not compilable.' \
        'The gtk/gtkwidget.h -> atk/atk.h include chain is incomplete.' \
        "GTK version:  $gtk_version" \
        "GTK pcfile:   $gtk_pcfiledir" \
        "ATK version:  $atk_version" \
        "ATK pcfile:   $atk_pcfiledir" \
        "ATK include:  $atk_includedir" \
        "GTK cflags:   $gtk_cflags" \
        "ATK cflags:   $atk_cflags" >&2
    exit 1
fi

cc_version="$("${cc_cmd[@]}" --version 2>&1 | sed -n '1p' || true)"
{
    printf 'SCHEMA=1\n'
    printf 'MACOS_HOST_ARCH=%s\n' "${MACOS_HOST_ARCH:-}"
    printf 'CC=%s\n' "$cc_value"
    printf 'CC_VERSION=%s\n' "$cc_version"
    printf 'PKG_CONFIG=%s\n' "$pkg_config_value"
    printf 'PKG_CONFIG_PATH=%s\n' "${PKG_CONFIG_PATH:-}"
    printf 'GTK_VERSION=%s\n' "$gtk_version"
    printf 'GTK_PCFILEDIR=%s\n' "$gtk_pcfiledir"
    printf 'GTK_CFLAGS=%s\n' "$gtk_cflags"
    printf 'GTK_LIBS=%s\n' "$gtk_libs"
    printf 'ATK_VERSION=%s\n' "$atk_version"
    printf 'ATK_PCFILEDIR=%s\n' "$atk_pcfiledir"
    printf 'ATK_INCLUDEDIR=%s\n' "$atk_includedir"
    printf 'ATK_CFLAGS=%s\n' "$atk_cflags"
} > "$candidate"

if [[ ! -f "$manifest" ]] || ! cmp -s "$candidate" "$manifest"; then
    if [[ -f "$BUILD_DIR/build.ninja" ]]; then
        rm -f "$BUILD_DIR/.whp-config"
        printf '%s\n' \
            'GTK/ATK dependency identity changed; forcing QEMU reconfiguration.' \
            "GTK pcfile: $gtk_pcfiledir" \
            "ATK pcfile: $atk_pcfiledir"
    fi
    mv "$candidate" "$manifest"
else
    rm -f "$candidate"
fi

printf '%s\n' \
    "GTK header probe:         usable ($gtk_version)" \
    "GTK pkg-config metadata:  $gtk_pcfiledir" \
    "ATK pkg-config metadata:  $atk_pcfiledir"
