#!/usr/bin/env bash
# SPDX-License-Identifier: GPL-2.0-or-later
set -euo pipefail
root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
seed="$root/seeds/install.sh"
bridge="$root/scripts/whp-build/seed-bin/install"
tmp="$(mktemp -d "${TMPDIR:-/tmp}/whp-install-regression.XXXXXX")"
trap 'rm -rf -- "$tmp"' EXIT

selected="$(env -u WHP_INSTALL_SEED -u WHP_INSTALL_LOCKED "$seed" --print-seed)"
[[ -x "$selected" ]]
[[ "$(WHP_INSTALL_SEED="$selected" "$seed" --print-seed)" == "$selected" ]]
WHP_INSTALL_SEED="$selected" "$seed" --check | grep -Fq 'replacement verified'

# The literal bridge uses exactly the same native implementation for data and
# executable installs, including spaces in destination paths.
mkdir "$tmp/tree"
printf 'payload\n' > "$tmp/source"
WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 "$bridge" -d -m 0755 "$tmp/tree/nested path"
WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 "$bridge" -c -m 0644 \
    "$tmp/source" "$tmp/tree/nested path/data"
[[ "$(cat "$tmp/tree/nested path/data")" == payload ]]
[[ ! -x "$tmp/tree/nested path/data" ]]
WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 "$bridge" -m 0755 \
    "$tmp/source" "$tmp/tree/nested path/tool"
[[ -x "$tmp/tree/nested path/tool" ]]

# Verify literal install resolves through PATH to the locked seed bridge,
# not a different Homebrew, MacPorts, or inherited host utility.
bridge_on_path="$(WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 \
    PATH="$root/scripts/whp-build/seed-bin:$PATH" \
    /bin/sh -c 'command -v install')"
[[ "$bridge_on_path" == "$bridge" ]]
WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 \
    PATH="$root/scripts/whp-build/seed-bin:$PATH" \
    /bin/sh -c 'install -m 0644 "$1" "$2"' whp-install-path \
        "$tmp/source" "$tmp/by-path"
[[ "$(cat "$tmp/by-path")" == payload ]]

python3 - "$tmp/tree/nested path" <<'PY'
from pathlib import Path
import stat
import sys
directory = Path(sys.argv[1])
for path, expected in ((directory, 0o755),
                       (directory / "data", 0o644),
                       (directory / "tool", 0o755)):
    actual = stat.S_IMODE(path.stat().st_mode)
    assert actual == expected, (path, oct(actual), oct(expected))
PY

# Explicit bad paths, false-success implementations, and self-references are
# errors, never prompts to silently rediscover a different host install.
if WHP_INSTALL_SEED=/no/such/install "$seed" --print-seed \
    >"$tmp/out" 2>"$tmp/error"; then
    printf 'error: unavailable install override accepted\n' >&2; exit 1
fi
grep -Fq 'WHP_INSTALL_SEED is not a usable host install' "$tmp/error"
cat > "$tmp/fake-install" <<'FAKE'
#!/bin/sh
exit 0
FAKE
chmod +x "$tmp/fake-install"
if WHP_INSTALL_SEED="$tmp/fake-install" "$seed" --print-seed \
    >"$tmp/out" 2>"$tmp/error"; then
    printf 'error: false-success install override accepted\n' >&2; exit 1
fi
grep -Fq 'failed directory creation' "$tmp/error"

# These broken installers produce correct content but ignore requested modes.
cat > "$tmp/bad-mode-install" <<'BADMODE'
#!/bin/sh
"$WHP_INSTALL_TEST_PROVIDER" "$@" || exit 1
for last do :; done
case "$WHP_BAD_MODE_STAGE:$1:${2:-}" in
    directory:-d:*) chmod 0700 "$last" ;;
    data:-c:*) chmod 0600 "$last" ;;
    executable:-m:0755) chmod 0644 "$last" ;;
    replacement:-m:0644) chmod 0600 "$last" ;;
esac
BADMODE
chmod +x "$tmp/bad-mode-install"
for stage in directory data executable replacement; do
    case "$stage" in
        directory) expected='failed directory creation' ;;
        data) expected='failed data copy or mode' ;;
        executable) expected='failed executable copy or mode' ;;
        replacement) expected='failed replacement' ;;
    esac
    if WHP_BAD_MODE_STAGE="$stage" WHP_INSTALL_TEST_PROVIDER="$selected" \
       WHP_INSTALL_SEED="$tmp/bad-mode-install" "$seed" --print-seed \
           >"$tmp/out" 2>"$tmp/error"; then
        printf 'error: bad %s mode accepted by install seed\n' "$stage" >&2
        exit 1
    fi
    if ! grep -Fq "$expected" "$tmp/error"; then
        printf 'error: wrong diagnostic for invalid %s installation mode\n' "$stage" >&2
        cat "$tmp/error" >&2
        exit 1
    fi
done

for bad in "$seed" "$bridge"; do
    if WHP_INSTALL_SEED="$bad" "$seed" --print-seed \
        >"$tmp/out" 2>"$tmp/error"; then
        printf 'error: recursive install adapter accepted\n' >&2; exit 1
    fi
done
for runner in "$seed" "$bridge"; do
    if WHP_INSTALL_LOCKED=1 WHP_INSTALL_SEED= "$runner" \
        "$tmp/source" "$tmp/unexpected" >"$tmp/out" 2>"$tmp/error"; then
        printf 'error: locked install without a seed accepted\n' >&2; exit 1
    fi
    grep -Fq 'locked install has no usable seed' "$tmp/error"
done

# Verbose tracing stays opt-in and on stderr; stdout/data are unchanged.
WHP_INSTALL_SEED="$selected" WHP_INSTALL_LOCKED=1 WHP_INSTALL_VERBOSE=1 \
    "$bridge" -m 0644 "$tmp/source" "$tmp/trace" \
    >"$tmp/out" 2>"$tmp/error"
[[ ! -s "$tmp/out" ]]
grep -Fq 'WHP install invocation:' "$tmp/error"

python3 - "$root/build.sh" <<'PY'
from pathlib import Path
import sys
source = Path(sys.argv[1]).read_text(encoding='utf-8')
assert 'WHP_INSTALL_SEED=$("$SOURCE_DIR/seeds/install.sh" --print-seed)' in source
assert 'WHP_INSTALL_LOCKED=1' in source
assert 'export WHP_INSTALL_SEED WHP_INSTALL_LOCKED' in source
assert source.index('WHP_INSTALL_SEED=$("$SOURCE_DIR/seeds/install.sh"') < source.index('whp_select_seed_git()')
assert 'INSTALL=$WHP_INSTALL_SEED' not in source  # Autotools owns its INSTALL variable.
PY
printf '%s\n' 'QEMU install seed regression: passed'
