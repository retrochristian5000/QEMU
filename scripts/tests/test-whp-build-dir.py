#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import platform
import tempfile
import unittest
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
MACOS_HYGIENE = ROOT / 'scripts' / 'macos-build-hygiene.bash'


def load_portable_build():
    spec = importlib.util.spec_from_file_location('whp_portable_build', PORTABLE_BUILD_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextmanager
def temporary_environment(updates, removals=()):
    old = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(old)
        for name in removals:
            os.environ.pop(name, None)
        os.environ.update(updates)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def canonical_arch(value: str) -> str:
    value = value.lower()
    if value in ('amd64', 'x86_64'):
        return 'x86_64'
    if value in ('aarch64', 'arm64'):
        return 'arm64'
    return value.replace(' ', '-').replace('/', '-')


def canonical_os(value: str) -> str:
    value = value.lower()
    if value == 'darwin':
        return 'apple-darwin'
    if value.startswith(('mingw', 'msys', 'cygwin')) or value == 'windows':
        return 'windows'
    return value.replace(' ', '-').replace('/', '-')


class WhpBuildDirectoryTests(unittest.TestCase):
    def test_relative_build_dir_is_source_relative(self):
        mod = load_portable_build()
        with temporary_environment(
            {
                'BUILD_DIR': 'out/portable-test',
                'BUILD_QEMU_IMG': '0',
                'BUILD_QEMU_SYSTEM_I386': '0',
                'BUILD_QEMU_SYSTEM_PPC': '0',
                'BUILD_OPENBIOS': 'n',
                'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
            }
        ):
            build_dir, _, _, _, _ = mod.build_plan(['qemu-img'])
        self.assertEqual(build_dir, ROOT / 'out' / 'portable-test')

    def test_default_build_dir_is_host_scoped_and_runner_neutral(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td, temporary_environment(
            {
                'HOME': td,
                'BUILD_QEMU_IMG': '0',
                'BUILD_QEMU_SYSTEM_I386': '0',
                'BUILD_QEMU_SYSTEM_PPC': '0',
                'BUILD_OPENBIOS': 'n',
                'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
            },
            removals=('BUILD_DIR', 'XDG_CACHE_HOME'),
        ):
            build_dir, _, _, _, _ = mod.build_plan(['qemu-img'])

        name = build_dir.name
        self.assertNotIn('portable', name)
        self.assertNotIn('ppc', name)
        self.assertIn(canonical_arch(platform.machine()), name)
        self.assertIn(canonical_os(platform.system()), name)

    def test_macos_hygiene_never_recursively_deletes_build_dir(self):
        content = MACOS_HYGIENE.read_text(encoding='utf-8')
        self.assertNotIn('rm -rf "$BUILD_DIR"', content)


if __name__ == '__main__':
    unittest.main()
