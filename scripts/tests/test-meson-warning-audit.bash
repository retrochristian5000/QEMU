#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
CHECKER="$ROOT_DIR/scripts/tests/check-meson-warnings.py"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

printf '%s\n' \
    'The Meson build system' \
    'Build targets in project: 42' > "$TMP/clean.log"
python3 "$CHECKER" "$TMP/clean.log"

printf '%s\n' \
    'meson.build:42: WARNING: deprecated build-system behavior' \
    > "$TMP/warning.log"
if python3 "$CHECKER" "$TMP/warning.log"; then
    echo 'error: Meson warning was accepted' >&2
    exit 1
fi

printf '%s\n' \
    'DEPRECATION: old API is deprecated' > "$TMP/deprecation.log"
if python3 "$CHECKER" "$TMP/deprecation.log"; then
    echo 'error: Meson deprecation was accepted' >&2
    exit 1
fi

# Compiler probes can legitimately write lowercase warnings into meson-log.txt.
# The audit is for Meson's own uppercase configuration diagnostics.
printf '%s\n' \
    'warning: compiler probe warning, expected inside meson-log.txt' \
    > "$TMP/compiler.log"
python3 "$CHECKER" "$TMP/compiler.log"

# Keep optional-dependency failures controlled by their own Meson option. A
# cap_ng/vde copy-and-paste mix-up used to turn an explicit VDE request into a
# warning, or make an unrelated cap_ng request turn VDE failure fatal.
vde_block="$(awk '
    /^vde = not_found$/ { in_vde=1 }
    in_vde { print }
    in_vde && /^pulse = not_found$/ { exit }
' "$ROOT_DIR/meson.build")"
if grep -Fq "get_option('cap_ng').enabled()" <<< "$vde_block"; then
    echo 'error: VDE link failure is controlled by cap_ng instead of vde' >&2
    exit 1
fi
if ! grep -Fq "if get_option('vde').enabled()" <<< "$vde_block"; then
    echo 'error: VDE link failure is not controlled by the vde option' >&2
    exit 1
fi

printf '%s\n' 'Meson warning audit regression test: ok'
