#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regress native Homebrew discovery before QEMU's late provider setup."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
build = (ROOT / "build.sh").read_text(encoding="utf-8")
make = (ROOT / "scripts/whp-build/gnu-make.bash").read_text(encoding="utf-8")

# The early Python seed, not build.sh, owns installed interpreter selection.
# Its Homebrew preference must precede generic PATH without depending on
# Homebrew itself. The public entry uses the seed before the later host tools.
python_seed = (ROOT / "seeds/python.sh").read_text(encoding="utf-8")
assert 'HOST_PYTHON=$(/bin/sh "$SOURCE_DIR/seeds/python.sh" --print-seed' in build
assert 'for variable in PYTHON WHP_PYTHON_SEED; do' in python_seed
assert 'if [ "$host_os" = macos ]; then' in python_seed
assert 'arm64|aarch64) brew_prefix=/opt/homebrew' in python_seed
assert 'x86_64) brew_prefix=/usr/local' in python_seed
assert '"$brew_prefix/bin/python3"' in python_seed
assert 'for requested in python3 python; do' in python_seed
assert python_seed.index('"$brew_prefix/bin/python3"') < python_seed.index(
    'for requested in python3 python; do')
assert build.index('if [ -n "${PYTHON:-}" ]; then') < build.index(
    'HOST_PYTHON=$(/bin/sh "$SOURCE_DIR/seeds/python.sh" --print-seed')
assert build.index('WHP_PYTHON_BOOTSTRAP_SEED=$HOST_PYTHON') < build.index(
    '. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"')

# GNU Make needs a validated seed before its managed bootstrap. Probe the
# architecture's Homebrew gmake, not the opposite (possibly Rosetta) prefix.
assert 'arm64|aarch64) whp_make_brew_prefix=/opt/homebrew' in make
assert 'x86_64) whp_make_brew_prefix=/usr/local' in make
assert '"$whp_make_brew_prefix/bin/gmake"' in make
assert '"$whp_make_brew_prefix/opt/make/bin/gmake"' in make
assert make.index('"$whp_make_brew_prefix/bin/gmake"') < make.index(
    'for whp_make_candidate in gmake make')
# The entrypoint preserves requested Make before deferring to its seed.
# Explicit seed/MAKE_CMD/MAKE overrides must precede automatic discovery.
make_seed = (ROOT / "seeds/make.sh").read_text(encoding="utf-8")
assert 'WHP_MAKE_REQUESTED=${MAKE_CMD:-${MAKE:-}}' in build
assert 'if [ -n "${WHP_MAKE_SEED:-}" ] || [ -n "$WHP_MAKE_REQUESTED" ]; then' in build
assert build.index('WHP_MAKE_REQUESTED=${MAKE_CMD:-${MAKE:-}}') < build.index(
    'MAKE_CMD=$(/bin/sh "$SOURCE_DIR/seeds/make.sh" --print-seed)')
assert make_seed.index('for setting in WHP_MAKE_SEED MAKE_CMD MAKE; do') < make_seed.index(
    'selected=$(whp_find_gnu_make)')

# The POSIX helper must stay sourceable on hosts without Homebrew.
result = subprocess.run(
    ["/bin/sh", "-c", f'. "{ROOT}/scripts/whp-build/gnu-make.bash"; '
                      'whp_find_gnu_make >/dev/null'],
    check=False, capture_output=True, text=True,
)
assert result.returncode in (0, 1), result.stderr

print("early Homebrew Python and GNU Make selection: wiring verified")
