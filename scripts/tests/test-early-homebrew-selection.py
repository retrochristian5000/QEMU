#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regress native Homebrew discovery before QEMU's late provider setup."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
build = (ROOT / "build.sh").read_text(encoding="utf-8")
make = (ROOT / "scripts/whp-build/gnu-make.bash").read_text(encoding="utf-8")

# The public shell entry must select a native Homebrew interpreter *before*
# generic PATH and before the late macOS host-tool provider is consulted.
assert 'if [ "$WHP_HOST_OS" = macos ]; then' in build
assert 'arm64|aarch64) whp_early_brew=/opt/homebrew' in build
assert 'x86_64) whp_early_brew=/usr/local' in build
assert '"$whp_early_brew/bin/python3"' in build
assert 'if [ -z "$HOST_PYTHON" ]; then' in build
assert build.index('"$whp_early_brew/bin/python3"') < build.index(
    'for python_name in python3 python')
assert build.index('if [ -n "${PYTHON:-}" ]; then') < build.index(
    '"$whp_early_brew/bin/python3"')
assert build.index('"$whp_early_brew/bin/python3"') < build.index(
    'whp_prepare_host_tools') if 'whp_prepare_host_tools' in build else True

# GNU Make needs a validated seed before its managed bootstrap. Probe the
# architecture's Homebrew gmake, not the opposite (possibly Rosetta) prefix.
assert 'arm64|aarch64) whp_make_brew_prefix=/opt/homebrew' in make
assert 'x86_64) whp_make_brew_prefix=/usr/local' in make
assert '"$whp_make_brew_prefix/bin/gmake"' in make
assert '"$whp_make_brew_prefix/opt/make/bin/gmake"' in make
assert make.index('"$whp_make_brew_prefix/bin/gmake"') < make.index(
    'for whp_make_candidate in gmake make')
assert build.index('if [ -n "$WHP_MAKE_REQUESTED" ]; then') < build.index(
    'MAKE_CMD=$(whp_find_gnu_make || true)')

# The POSIX helper must stay sourceable on hosts without Homebrew.
result = subprocess.run(
    ["/bin/sh", "-c", f'. "{ROOT}/scripts/whp-build/gnu-make.bash"; '
                      'whp_find_gnu_make >/dev/null'],
    check=False, capture_output=True, text=True,
)
assert result.returncode in (0, 1), result.stderr

print("early Homebrew Python and GNU Make selection: wiring verified")
