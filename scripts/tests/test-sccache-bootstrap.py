#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline regression coverage for WHP's managed sccacher bootstrap."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'ensure-sccache.py'

spec = importlib.util.spec_from_file_location('whp_ensure_sccache', BOOTSTRAP)
bootstrap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bootstrap)


class ManagedSccacheTests(unittest.TestCase):
    def test_cargo_build_is_memory_conservative(self):
        env = bootstrap.cargo_environment({
            'RUSTC_WRAPPER': '/old/sccache',
            'CARGO_BUILD_RUSTC_WRAPPER': '/other/cache',
            'CARGO_ENCODED_RUSTFLAGS': '-Copt-level=3',
            'SCCACHE_DIR': '/cache',
        }, pathlib.Path('/tmp/sccache-target'))
        self.assertNotIn('RUSTC_WRAPPER', env)
        self.assertNotIn('CARGO_BUILD_RUSTC_WRAPPER', env)
        self.assertNotIn('CARGO_ENCODED_RUSTFLAGS', env)
        self.assertEqual(env['CARGO_PROFILE_RELEASE_LTO'], 'false')
        self.assertEqual(env['CARGO_PROFILE_RELEASE_CODEGEN_UNITS'], '8')
        self.assertEqual(env['CARGO_TARGET_DIR'], '/tmp/sccache-target')
        self.assertEqual(env['SCCACHE_DIR'], '/cache')

    def test_job_override_is_strict(self):
        self.assertEqual(bootstrap.build_jobs({}), 2)
        self.assertEqual(bootstrap.build_jobs({'WHP_SCCACHE_BUILD_JOBS': '1'}), 1)
        for bad in ('', '0', '-1', '1 2', '2x'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                bootstrap.build_jobs({'WHP_SCCACHE_BUILD_JOBS': bad})

    def test_source_is_pinned_submodule(self):
        modules = (ROOT / '.gitmodules').read_text(encoding='utf-8')
        self.assertIn('[submodule "toolchains/sccacher"]', modules)
        self.assertIn('https://github.com/retrochristian5000/sccacher.git', modules)
        self.assertEqual(bootstrap.SUBMODULE, pathlib.Path('toolchains/sccacher'))
        source = BOOTSTRAP.read_text(encoding='utf-8')
        self.assertIn("'ls-tree', 'HEAD'", source)
        self.assertIn("'--locked'", source)
        self.assertIn("'--no-default-features'", source)

    def test_cached_binary_skips_cargo(self):
        with tempfile.TemporaryDirectory() as directory:
            build = pathlib.Path(directory)
            host = f'{bootstrap.platform.system().lower()}-{bootstrap.platform.machine().lower()}'
            prefix = build / 'toolchains' / 'sccache' / host
            binary = prefix / 'bin' / 'sccache'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\necho sccache-0.18.0\n', encoding='utf-8')
            binary.chmod(0o755)
            identity = {
                'schema': bootstrap.SCHEMA, 'gitlink': 'a' * 40,
                'rustc': 'rustc 1.91.0', 'cargo': 'cargo 1.91.0',
                'features': 'local-only', 'profile': 'lto=false,codegen-units=8,debug=0',
            }
            (prefix / '.whp-sccacher.json').write_text(json.dumps(identity))
            with mock.patch.object(bootstrap, 'pinned_source', return_value=(build, 'a' * 40)), \
                 mock.patch.object(bootstrap, 'host_tools', return_value=('cargo', 'rustc 1.91.0', 'cargo 1.91.0')), \
                 mock.patch.object(bootstrap, 'call', return_value='sccache-0.18.0') as run:
                self.assertEqual(bootstrap.ensure(build), binary)
                run.assert_called_once_with([str(binary), '--version'], capture=True)

    def test_qemu_selects_fork_before_native_llvm(self):
        text = (ROOT / 'build.sh').read_text(encoding='utf-8')
        self.assertLess(text.index('scripts/ensure-sccache.py'),
                        text.index('scripts/bootstrap-native-clang.sh'))
        self.assertIn('WHP_COMPILER_CACHE_CMD=$(', text)
        self.assertIn('COMPILER_CACHE=sccache', text)


if __name__ == '__main__':
    unittest.main()
