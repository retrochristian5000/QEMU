#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITMODULES = ROOT / '.gitmodules'
CONFIG = ROOT / 'scripts' / 'whp-config' / 'config.py'
BUILD_ENTRY = ROOT / 'build.sh'
BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'
NATIVE_LLVM_BOOTSTRAP = ROOT / 'scripts' / 'bootstrap-native-clang.bash'


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

    config = CONFIG.read_text(encoding='utf-8')
    require(
        config,
        "Option('BOOTSTRAP_NINJA', 'Host features', 'Bootstrap/use WHP Ninja', 'choice', 'auto', ('auto', 'y', 'n'))",
        'menuconfig Ninja bootstrap policy',
    )
    require(config, "'BOOTSTRAP_NINJA',", 'Ninja tri-state shell export')

    entry = BUILD_ENTRY.read_text(encoding='utf-8')
    require(entry, 'scripts/ensure-ninja.py', 'bundled Ninja resolver hook')
    require(entry, 'BOOTSTRAP_NINJA=${BOOTSTRAP_NINJA:-auto}', 'Ninja bootstrap default')
    require(entry, '[ "$BOOTSTRAP_NINJA" != 1 ]', 'forced bundled Ninja policy')
    require(entry, '[ "$BOOTSTRAP_NINJA" != 0 ]', 'disabled bundled Ninja policy')
    require(entry, 'NINJA_CMD=', 'Ninja command export')
    require(entry, 'NINJA=$NINJA_CMD', 'QEMU Ninja environment handoff')
    require(entry, 'export NINJA_CMD NINJA PATH', 'Ninja PATH propagation before configure')

    if not BOOTSTRAP.is_file():
        raise SystemExit(f'error: bundled Ninja bootstrap is missing: {BOOTSTRAP}')
    bootstrap = BOOTSTRAP.read_text(encoding='utf-8')
    require(bootstrap, 'toolchains/ninja-builder', 'pinned Ninja source path')
    require(bootstrap, 'submodule', 'lazy submodule initialization')
    require(bootstrap, '--bootstrap', 'Ninja self-bootstrap mode')
    require(bootstrap, 'NINJA_GIT_COMMIT=', 'Ninja cache revision identity')
    require(bootstrap, 'NINJA_BOOTSTRAP_SCHEMA=', 'Ninja cache schema')
    require(bootstrap, 'CXX_VERSION=', 'host compiler cache identity')
    require(bootstrap, 'shutil.copytree(', 'read-only Ninja source staging')
    require(bootstrap, "staged_source / 'configure.py'", 'bootstrap from staged source copy')

    native_bootstrap = NATIVE_LLVM_BOOTSTRAP.read_text(encoding='utf-8')
    require(
        native_bootstrap,
        'ninja_cmd="${NINJA_CMD:-${NINJA:-ninja}}"',
        'native LLVM selected Ninja handoff',
    )
    require(
        native_bootstrap,
        '"-DCMAKE_MAKE_PROGRAM=$ninja_cmd"',
        'native LLVM CMake Ninja pin',
    )

    print('bundled Ninja selection policy: verified')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())