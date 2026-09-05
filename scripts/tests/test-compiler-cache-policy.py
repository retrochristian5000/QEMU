#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
NINJA_BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'
PREPARE_BUILD = ROOT / 'scripts' / 'whp-build' / 'prepare-build.bash'


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class CompilerCachePolicyTests(unittest.TestCase):
    def test_menu_exposes_compiler_cache_choice(self):
        config = load_module(CONFIG_TOOL, 'whp_config_cache_test')
        option = config.OPTION_BY_KEY['COMPILER_CACHE']
        self.assertEqual(option.section, 'Host features')
        self.assertEqual(option.label, 'Compiler cache')
        self.assertEqual(option.kind, 'choice')
        self.assertEqual(option.default, 'auto')
        self.assertEqual(option.choices, ('auto', 'ccache', 'sccache', 'none'))

    def test_cache_choice_is_exported_without_boolean_reencoding(self):
        config = load_module(CONFIG_TOOL, 'whp_config_cache_export_test')
        values = config.default_values()
        values['COMPILER_CACHE'] = 'sccache'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertIn("COMPILER_CACHE='sccache'", assignments)

        values['COMPILER_CACHE'] = 'auto'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertNotIn('COMPILER_CACHE=', assignments)

    def test_ninja_auto_cache_prefers_ccache_then_sccache(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_cache_auto_test')

        def both(name: str):
            return {'ccache': '/opt/bin/ccache', 'sccache': '/opt/bin/sccache'}.get(name)

        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(ninja.shutil, 'which', side_effect=both):
            self.assertEqual(ninja.select_compiler_cache(), '/opt/bin/ccache')

        def only_sccache(name: str):
            return {'sccache': '/opt/bin/sccache'}.get(name)

        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(ninja.shutil, 'which', side_effect=only_sccache):
            self.assertEqual(ninja.select_compiler_cache(), '/opt/bin/sccache')

    def test_ninja_explicit_cache_and_none_are_stable(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_cache_explicit_test')
        with mock.patch.dict(os.environ, {'COMPILER_CACHE': 'none'}, clear=True):
            self.assertEqual(ninja.select_compiler_cache(), '')

        with mock.patch.dict(os.environ, {'COMPILER_CACHE': 'sccache'}, clear=True), \
             mock.patch.object(ninja.shutil, 'which', return_value='/usr/local/bin/sccache'):
            self.assertEqual(ninja.select_compiler_cache(), '/usr/local/bin/sccache')

    def test_ninja_bootstrap_uses_cache_and_helper_only_macos_ldflags(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_cache_env_test')
        cache_dir = pathlib.Path('/tmp/whp-cache')
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(ninja.platform, 'system', return_value='Darwin'):
            env = ninja.bootstrap_environment(
                '/usr/bin/clang++',
                '/SDKs/MacOSX.sdk',
                '/opt/bin/ccache',
                cache_dir,
            )

        self.assertEqual(env['CXX'], '/opt/bin/ccache /usr/bin/clang++')
        self.assertEqual(env['CCACHE_DIR'], str(cache_dir))
        self.assertEqual(env['CXXFLAGS'], '-isysroot /SDKs/MacOSX.sdk')
        self.assertEqual(
            env['LDFLAGS'],
            '-isysroot /SDKs/MacOSX.sdk -Wl,-dead_strip',
        )
        self.assertNotIn('-Wl,-dead_strip', env['CXXFLAGS'])

    def test_qemu_host_policy_consumes_menu_cache_without_packaging_it(self):
        text = PREPARE_BUILD.read_text(encoding='utf-8')
        self.assertIn('COMPILER_CACHE="${COMPILER_CACHE:-auto}"', text)
        self.assertIn('WHP_COMPILER_CACHE_CMD', text)
        self.assertIn('.whp-compiler-cache', text)
        self.assertIn('ccache|sccache', text)
        self.assertNotIn('configure_args+=(--compiler-cache', text)


if __name__ == '__main__':
    unittest.main()
