#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail

root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
seed="$root/seeds/chmod.sh"
bridge="$root/scripts/whp-build/seed-bin/chmod"
tmp="$(umask 077; mktemp -d "${TMPDIR:-/tmp}/whp-chmod-regression.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

selected="$(env -u WHP_CHMOD_SEED -u WHP_CHMOD_LOCKED /bin/sh "$seed" --print-seed)"
[[ -x "$selected" ]]
[[ "$(WHP_CHMOD_SEED="$selected" /bin/sh "$seed" --print-seed)" == "$selected" ]]
WHP_CHMOD_SEED="$selected" /bin/sh "$seed" --check |
    grep -Fq 'numeric, symbolic, recursive, symlink isolation verified'

file="$tmp/file with spaces"
printf '%s\n' unchanged > "$file"
WHP_CHMOD_SEED="$selected" WHP_CHMOD_LOCKED=1 "$bridge" 0600 "$file"
WHP_CHMOD_SEED="$selected" WHP_CHMOD_LOCKED=1 \
    PATH="$root/scripts/whp-build/seed-bin:$PATH" \
    /bin/sh -c 'chmod u+x "$1"' whp-chmod "$file"
python3 - "$file" <<'PY'
from pathlib import Path
import stat
import sys
path = Path(sys.argv[1])
assert stat.S_IMODE(path.stat().st_mode) == 0o700
assert path.read_text() == "unchanged\n"
PY

# Locking must not reprobe or rewrite the argument vector.
mkdir "$tmp/tools with spaces"
cat > "$tmp/tools with spaces/gchmod" <<'FAKE'
#!/bin/sh
printf '%s\n' "$@" >> "$WHP_CHMOD_TEST_LOG"
exec "$WHP_CHMOD_TEST_PROVIDER" "$@"
FAKE
"$selected" 0700 "$tmp/tools with spaces/gchmod"
export WHP_CHMOD_TEST_LOG="$tmp/log" WHP_CHMOD_TEST_PROVIDER="$selected"
override="$tmp/tools with spaces/gchmod"
[[ "$(WHP_CHMOD_SEED="$override" /bin/sh "$seed" --print-seed)" == "$override" ]]
: > "$WHP_CHMOD_TEST_LOG"
WHP_CHMOD_SEED="$override" WHP_CHMOD_LOCKED=1 "$bridge" u-x "$file"
printf '%s\n' u-x "$file" > "$tmp/expected"
cmp "$tmp/expected" "$WHP_CHMOD_TEST_LOG"

cat > "$tmp/false-success" <<'FAKE'
#!/bin/sh
exit 0
FAKE
"$selected" 0700 "$tmp/false-success"
ln -s "$seed" "$tmp/seed-alias"
ln -s "$bridge" "$tmp/bridge-alias"
for bad in /nonexistent/chmod "$tmp/false-success" "$seed" "$bridge" \
    "$tmp/seed-alias" "$tmp/bridge-alias"; do
    if WHP_CHMOD_SEED="$bad" /bin/sh "$seed" --print-seed > "$tmp/out" 2> "$tmp/error"; then
        printf 'error: invalid chmod seed accepted: %s\n' "$bad" >&2
        exit 1
    fi
    grep -Fq 'WHP_CHMOD_SEED is not a usable host chmod' "$tmp/error"
done
for runner in "$seed" "$bridge"; do
    for bad in "" "$seed" "$bridge" "$tmp/seed-alias" "$tmp/bridge-alias"; do
        if WHP_CHMOD_SEED="$bad" WHP_CHMOD_LOCKED=1 "$runner" 0777 "$file" \
            > "$tmp/out" 2> "$tmp/error"; then
            printf 'error: locked chmod accepted recursive or empty provider\n' >&2
            exit 1
        fi
        grep -Fq 'error: locked chmod' "$tmp/error"
    done
done
if WHP_CHMOD_SEED="$selected" WHP_CHMOD_LOCKED=1 "$bridge" 0600 "$tmp/missing" \
    > "$tmp/out" 2> "$tmp/error"; then
    printf 'error: missing chmod operand reported success\n' >&2
    exit 1
fi
python3 - "$file" "$root/build.sh" <<'PY'
from pathlib import Path
import stat
import sys
assert stat.S_IMODE(Path(sys.argv[1]).stat().st_mode) == 0o600
build = Path(sys.argv[2]).read_text()
assert 'WHP_CHMOD_SEED=$("$SOURCE_DIR/seeds/chmod.sh" --print-seed)' in build
assert 'export WHP_CHMOD_SEED WHP_CHMOD_LOCKED' in build
assert build.index('WHP_CHMOD_SEED=$(') < build.index('whp_select_seed_git()')
PY
printf '%s\n' 'QEMU chmod seed regression: passed'
