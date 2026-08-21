#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITMODULES = ROOT / '.gitmodules'
BUILD_ENTRY = ROOT / 'build.sh'
BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f'error: missing {label}: {needle}')


def main() -> int:
    gitmodules = GITMODULES.read_text(encoding='utf-8')
    require(gitmodules, '[submodule "toolchains/ninja-builder"]', 'Ninja submodule declaration')
    require(gitmodules, 'path = toolchains/ninja-builder', 'Ninja submodule path')
    require(
        gitmodules,
        'url = https://github.com/retrochristian5000/ninja-builder.git',
        'Ninja fork URL',
    )

    entry = BUILD_ENTRY.read_text(encoding='utf-8')
    require(entry, 'scripts/ensure-ninja.py', 'bundled Ninja resolver hook')
    require(entry, 'NINJA_CMD=', 'Ninja command export')
    require(entry, 'export NINJA_CMD PATH', 'Ninja PATH propagation before configure')

    if not BOOTSTRAP.is_file():
        raise SystemExit(f'error: bundled Ninja bootstrap is missing: {BOOTSTRAP}')
    bootstrap = BOOTSTRAP.read_text(encoding='utf-8')
    require(bootstrap, 'toolchains/ninja-builder', 'pinned Ninja source path')
    require(bootstrap, 'submodule', 'lazy submodule initialization')
    require(bootstrap, '--bootstrap', 'Ninja self-bootstrap mode')
    require(bootstrap, 'NINJA_GIT_COMMIT=', 'Ninja cache revision identity')
    require(bootstrap, 'NINJA_BOOTSTRAP_SCHEMA=', 'Ninja cache schema')
    require(bootstrap, 'CXX_VERSION=', 'host compiler cache identity')

    print('bundled Ninja fallback policy: verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
