#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
MENU="$ROOT/scripts/whp-config/menuconfig.sh"
SCHEMA="$ROOT/scripts/whp-config/menu-options.def"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
CONFIG="$TMP/.whpconfig"

dump="$(/bin/sh "$MENU" "$CONFIG" --dump)"
grep -Fq 'Bootstrap/use WHP Python' <<< "$dump"
grep -Eq 'BOOTSTRAP_PYTHON[[:space:]]+auto$' <<< "$dump"

number="$(
    awk -F '|' '
        $0 !~ /^#/ && NF >= 5 {
            count++
            if ($1 == "BOOTSTRAP_PYTHON") {
                print count
                exit
            }
        }
    ' "$SCHEMA"
)"
[[ -n "$number" ]]

printf '%s\ns\nq\n' "$number" | /bin/sh "$MENU" "$CONFIG" >/dev/null
grep -Fxq 'BOOTSTRAP_PYTHON=y' "$CONFIG"

printf 'no-Python menuconfig smoke test: passed\n'
