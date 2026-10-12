#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
NINJA_BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'
BUILD_WRAPPER = ROOT / 'builder.sh'


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
            '-isysroot /SDKs/MacOSX.sdk -Wl,-O2 -Wl,-dead_strip',
        )
        self.assertNotIn('-Wl,-dead_strip', env['CXXFLAGS'])

    def test_ninja_bootstrap_strips_inherited_search_environment(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_env_hygiene_test')
        inherited = {
            'CPATH': '/tmp/foreign/include',
            'C_INCLUDE_PATH': '/tmp/foreign/c-include',
            'CPLUS_INCLUDE_PATH': '/tmp/foreign/cxx-include',
            'LIBRARY_PATH': '/tmp/foreign/lib',
            'DYLD_LIBRARY_PATH': '/tmp/foreign/dyld',
            'CMAKE_PREFIX_PATH': '/tmp/foreign/cmake',
            'ARCHFLAGS': '-arch x86_64',
        }
        with mock.patch.dict(os.environ, inherited, clear=True):
            env = ninja.bootstrap_environment('/usr/bin/clang++', '')

        for key in inherited:
            self.assertNotIn(key, env, key)

    def test_sccache_daemon_idle_policy_respects_user_configuration(self):
        policy = ROOT / 'scripts' / 'whp-build' / 'sccache-policy.sh'
        shell = '. "$1"; whp_sccache_memory_policy; ' \
                'printf "%s|%s|%s" "${SCCACHE_IDLE_TIMEOUT-unset}" ' \
                '"${SCCACHE_CACHE_SIZE-unset}" "${SCCACHE_CLIENT_SIDE-unset}"'

        def run(vars):
            return subprocess.run(
                ['/bin/sh', '-c', shell, 'sh', str(policy)],
                env=vars, text=True, capture_output=True,
            )

        result = run({})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '180|unset|unset')

        result = run({'SCCACHE_IDLE_TIMEOUT': '0',
                      'SCCACHE_CACHE_SIZE': '4G',
                      'SCCACHE_CLIENT_SIDE': '0'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, '0|4G|0')

        result = run({'SCCACHE_CONF': '/tmp/whp-custom-sccache.toml'})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, 'unset|unset|unset')

        result = run({'SCCACHE_IDLE_TIMEOUT': 'not-seconds'})
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('SCCACHE_IDLE_TIMEOUT must be seconds', result.stderr)

    def test_sccache_ninja_bootstrap_inherits_idle_and_client_overrides(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_sccache_env_test')
        cache_dir = pathlib.Path('/tmp/whp-sccache')

        with mock.patch.dict(os.environ, {}, clear=True):
            env = ninja.bootstrap_environment(
                '/usr/bin/clang++', '', '/opt/bin/sccache', cache_dir,
            )
        self.assertEqual(env['SCCACHE_DIR'], str(cache_dir))
        self.assertEqual(env['SCCACHE_IDLE_TIMEOUT'], '180')
        self.assertNotIn('SCCACHE_CLIENT_SIDE', env)

        with mock.patch.dict(os.environ, {
            'SCCACHE_IDLE_TIMEOUT': '0',
            'SCCACHE_CLIENT_SIDE': '1',
            'SCCACHE_CACHE_SIZE': '3G',
        }, clear=True):
            env = ninja.bootstrap_environment(
                '/usr/bin/clang++', '', '/opt/bin/sccache', cache_dir,
            )
        self.assertEqual(env['SCCACHE_IDLE_TIMEOUT'], '0')
        self.assertEqual(env['SCCACHE_CLIENT_SIDE'], '1')
        self.assertEqual(env['SCCACHE_CACHE_SIZE'], '3G')

        with mock.patch.dict(os.environ, {
            'SCCACHE_CONF': '/tmp/sccache.conf',
        }, clear=True):
            env = ninja.bootstrap_environment(
                '/usr/bin/clang++', '', '/opt/bin/sccache', cache_dir,
            )
        self.assertNotIn('SCCACHE_IDLE_TIMEOUT', env)

        with mock.patch.dict(os.environ, {
            'SCCACHE_IDLE_TIMEOUT': '20m',
        }, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'SCCACHE_IDLE_TIMEOUT'):
                ninja.bootstrap_environment(
                    '/usr/bin/clang++', '', '/opt/bin/sccache', cache_dir,
                )

    def test_sccache_cache_roots_align_with_shell_wrappers(self):
        ninja = NINJA_BOOTSTRAP.read_text(encoding='utf-8')
        native = (ROOT / 'scripts' / 'bootstrap-native-clang.bash').read_text(
            encoding='utf-8')
        wrapper = BUILD_WRAPPER.read_text(encoding='utf-8')
        for source in (native, wrapper):
            self.assertIn('sccache-policy.sh', source)
            self.assertIn('whp_sccache_memory_policy', source)
            self.assertIn('sccache-$cache_tag', source)
        self.assertIn("cache_tag = f'{platform.system()}-{platform.machine()}'", ninja)
        self.assertIn("requested = os.environ.get('SCCACHE_DIR')", ninja)
        self.assertIn("'WHP_COMPILER_CACHE_ROOT'", ninja)

    def test_qemu_host_cache_is_build_time_only(self):
        text = BUILD_WRAPPER.read_text(encoding='utf-8')
        self.assertIn('COMPILER_CACHE=${COMPILER_CACHE:-auto}', text)
        self.assertIn('WHP_COMPILER_CACHE_CMD', text)
        self.assertIn('.whp-compiler-cache', text)
        self.assertIn('ccache|sccache', text)
        self.assertIn('CCACHE_DISABLE=1', text)
        self.assertNotIn('--compiler-cache', text)
        self.assertNotIn('PREFIX/.whp-compiler-cache', text)


if __name__ == '__main__':
    unittest.main()
