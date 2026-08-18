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

printf '%s\n' 'Meson warning audit regression test: ok'
