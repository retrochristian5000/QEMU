#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
# Pre-managed CPython root selection, isolation and passthrough.
set -euo pipefail

ROOT="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
SEED="$ROOT/seeds/python.sh"
TMP="$(mktemp -d)"
trap 'rm -rf -- "$TMP"' EXIT
/bin/sh -n "$SEED"
[[ "$(/bin/sh "$SEED" --whp-python-adapter-probe)" == whp-qemu-python-seed-adapter ]]

cat > "$TMP/banner-only" <<'EOF'
#!/bin/sh
if [ "$1" = --version ]; then printf '%s\n' 'Python 99.99'; fi
exit 0
EOF
chmod +x "$TMP/banner-only"
ln -s "$SEED" "$TMP/recursive"

for invalid in "$SEED" "$TMP/recursive" "$TMP/banner-only" /bin/false "$TMP/missing" 'python3 -I'; do
    if PYTHON="$invalid" WHP_PYTHON_SEED= /bin/sh "$SEED" --print-seed \
            >"$TMP/out" 2>"$TMP/err"; then
        printf 'error: invalid explicit Python seed accepted: %s\n' "$invalid" >&2
        exit 1
    fi
    [[ ! -s "$TMP/out" ]]
    grep -Fq 'PYTHON must select native Python' "$TMP/err"
done
if PYTHON= WHP_PYTHON_SEED=/bin/false /bin/sh "$SEED" --print-seed \
        >"$TMP/out" 2>"$TMP/err"; then
    printf '%s\n' 'error: invalid WHP_PYTHON_SEED fell back silently' >&2
    exit 1
fi
grep -Fq 'WHP_PYTHON_SEED must select native Python' "$TMP/err"
[[ ! -s "$TMP/out" ]]

real_python="$(command -v python3)"
[[ -n "$real_python" ]]
selected="$(PYTHON="$real_python" WHP_PYTHON_SEED= /bin/sh "$SEED" --print-seed)"
[[ -x "$selected" ]]
PYTHON="$selected" WHP_PYTHON_SEED= /bin/sh "$SEED" --check |
    grep -Fq 'runtime and venv verified'
result="$(PYTHON="$selected" WHP_PYTHON_SEED= /bin/sh "$SEED" -c 'print(101+2)')"
[[ "$result" == 103 ]]
if PYTHON="$selected" /bin/sh "$SEED" -c 'raise SystemExit(19)'; then
    printf '%s\n' 'error: Python seed hid an exit failure' >&2
    exit 1
else
    [[ "$?" -eq 19 ]]
fi
auto="$(PYTHON= WHP_PYTHON_SEED= /bin/sh "$SEED" --print-seed)"
[[ -x "$auto" ]]

# The seed is selection only: no managed source checkout or interpreter build.
[[ ! -e "$TMP/python-runtime" ]]
printf '%s\n' 'WHP independent Python seed contract: verified'
