#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
NINJA_BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'
PORTABLE_BUILD = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
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
        self.assertEqual(
            option.choices,
            ('auto', 'ccache', 'sccache', 'managed-sccache', 'none'),
        )
        self.assertNotIn('BOOTSTRAP_SCCACHE', config.OPTION_BY_KEY)

    def test_cache_choice_is_exported_without_boolean_reencoding(self):
        config = load_module(CONFIG_TOOL, 'whp_config_cache_export_test')
        values = config.default_values()
        values['COMPILER_CACHE'] = 'sccache'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertIn("COMPILER_CACHE='sccache'", assignments)

        values['COMPILER_CACHE'] = 'auto'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertNotIn('COMPILER_CACHE=', assignments)

    def test_legacy_managed_cache_profiles_migrate_without_file_writes(self):
        config = load_module(CONFIG_TOOL, 'whp_config_cache_migration_test')
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / '.whpconfig'
            for old, selected, expected in (
                ('y', 'auto', 'managed-sccache'),
                ('y', 'sccache', 'managed-sccache'),
                ('n', 'sccache', 'sccache'),
            ):
                with self.subTest(old=old, selected=selected):
                    original = (
                        'WHP_CONFIG_VERSION=3\n'
                        f'BOOTSTRAP_SCCACHE={old}\n'
                        f'COMPILER_CACHE={selected}\n'
                    )
                    path.write_text(original, encoding='utf-8')
                    state = config.load_config(path)
                    self.assertEqual(state.values['COMPILER_CACHE'], expected)
                    self.assertNotIn('BOOTSTRAP_SCCACHE', state.unknown)
                    self.assertEqual(path.read_text(encoding='utf-8'), original)
                    assignments = config.shell_assignments(state, {})
                    self.assertNotIn('BOOTSTRAP_SCCACHE=', assignments)
                    self.assertIn(f"COMPILER_CACHE='{expected}'", assignments)
                    config.save_config(path, state)
                    self.assertNotIn('BOOTSTRAP_SCCACHE=', path.read_text())
                    self.assertIn(f'COMPILER_CACHE={expected}', path.read_text())

    def test_legacy_managed_cache_conflicts_fail_before_rewrite(self):
        config = load_module(CONFIG_TOOL, 'whp_config_cache_conflict_test')
        with tempfile.TemporaryDirectory() as directory:
            path = pathlib.Path(directory) / '.whpconfig'
            for selected in ('ccache', 'none'):
                original = (
                    'WHP_CONFIG_VERSION=3\n'
                    'BOOTSTRAP_SCCACHE=y\n'
                    f'COMPILER_CACHE={selected}\n'
                )
                path.write_text(original, encoding='utf-8')
                with self.assertRaisesRegex(ValueError, 'conflicts'):
                    config.load_config(path)
                self.assertEqual(path.read_text(encoding='utf-8'), original)

    def test_managed_cache_choice_resolves_to_legacy_bootstrap_stage(self):
        build = (ROOT / 'build.sh').read_text(encoding='utf-8')
        start = build.index('# The retired BOOTSTRAP_SCCACHE menu toggle')
        end = build.index('\n# PGO use implies', start)
        script = (
            'set -eu\n' + build[start:end] +
            '\nprintf "cache=%s bootstrap=%s\\n" '
            '"${COMPILER_CACHE:-unset}" "${BOOTSTRAP_SCCACHE:-unset}"\n'
        )
        for cache, old, expected, succeeds in (
            ('managed-sccache', '', 'cache=sccache bootstrap=1', True),
            ('managed-sccache', '1', 'cache=sccache bootstrap=1', True),
            ('managed-sccache', '0', 'conflicts', False),
            ('sccache', '', 'cache=sccache bootstrap=unset', True),
        ):
            with self.subTest(cache=cache, old=old):
                env = {**os.environ, 'COMPILER_CACHE': cache}
                if old:
                    env['BOOTSTRAP_SCCACHE'] = old
                else:
                    env.pop('BOOTSTRAP_SCCACHE', None)
                proc = subprocess.run(
                    ['/bin/sh', '-c', script],
                    env=env, text=True, capture_output=True, check=False,
                )
                self.assertEqual(proc.returncode == 0, succeeds, proc.stderr)
                self.assertIn(expected, proc.stdout if succeeds else proc.stderr)

    def test_direct_portable_core_cannot_silently_skip_managed_cache(self):
        config = load_module(CONFIG_TOOL, 'whp_config_managed_direct_test')
        portable = load_module(PORTABLE_BUILD, 'whp_portable_managed_direct_test')
        with tempfile.TemporaryDirectory() as directory:
            profile = pathlib.Path(directory) / '.whpconfig'
            profile.write_text(
                'WHP_CONFIG_VERSION=3\nCOMPILER_CACHE=managed-sccache\n',
                encoding='utf-8',
            )
            with mock.patch.object(portable, 'USER_CONFIG', profile), \
                 mock.patch.dict(os.environ, {'COMPILER_CACHE': 'managed-sccache'}):
                with self.assertRaisesRegex(RuntimeError, 'requires the build.sh launcher'):
                    portable.resolved_values()
            # One-run overrides remain authoritative: auto does not request
            # a managed fork in the portable core.
            with mock.patch.object(portable, 'USER_CONFIG', profile), \
                 mock.patch.dict(os.environ, {'COMPILER_CACHE': 'auto'}):
                self.assertEqual(portable.resolved_values()['COMPILER_CACHE'], 'auto')

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

    def test_ninja_cache_override_must_match_policy_and_be_executable(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_cache_boundary_test')
        with tempfile.TemporaryDirectory() as directory:
            cache = pathlib.Path(directory) / 'ccache'
            cache.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            cache.chmod(0o755)
            explicit = {'WHP_COMPILER_CACHE_CMD': str(cache)}

            with mock.patch.dict(os.environ, {**explicit, 'COMPILER_CACHE': 'none'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'conflicts'):
                    ninja.select_compiler_cache()
            with mock.patch.dict(os.environ, {**explicit, 'COMPILER_CACHE': 'sccache'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'conflicts'):
                    ninja.select_compiler_cache()
            with mock.patch.dict(os.environ, {**explicit, 'COMPILER_CACHE': 'ccache'}, clear=True):
                self.assertEqual(ninja.select_compiler_cache(), str(cache))

            cache.chmod(0o644)
            with mock.patch.dict(os.environ, {**explicit, 'COMPILER_CACHE': 'ccache'}, clear=True):
                with self.assertRaisesRegex(RuntimeError, 'not executable'):
                    ninja.select_compiler_cache()

    def test_shell_cache_handoffs_reject_inherited_conflicts(self):
        runner = BUILD_WRAPPER.read_text(encoding='utf-8')
        prefix, separator, _ = runner.partition(
            '\n. "$script_dir/scripts/whp-build/shell-functions.sh"'
        )
        self.assertTrue(separator)
        native = (ROOT / 'scripts' / 'bootstrap-native-clang.bash').read_text(
            encoding='utf-8')
        start = native.index('COMPILER_CACHE="${COMPILER_CACHE:-auto}"')
        end = native.index('\ncmake_host_args=()', start)
        segments = (('/bin/sh', prefix), ('bash', 'set -euo pipefail\n' + native[start:end]))

        for shell, body in segments:
            for policy, override, succeeds in (
                ('none', '', True),
                ('none', '/unused/sccache', False),
                ('sccache', '/unused/ccache', False),
            ):
                with self.subTest(shell=shell, policy=policy, override=override):
                    env = {**os.environ, 'COMPILER_CACHE': policy,
                           'WHP_BUILD_ENTRY_NORMALIZED': '1', 'CC': 'cc', 'CXX': 'c++'}
                    if override:
                        env['WHP_COMPILER_CACHE_CMD'] = override
                    else:
                        env.pop('WHP_COMPILER_CACHE_CMD', None)
                    # The extracted builder entry needs the real script
                    # pathname as $0, just as a direct builder.sh invocation
                    # would supply before the compiler-cache policy runs.
                    completed = subprocess.run(
                        [shell, '-c', body, str(BUILD_WRAPPER)], cwd=ROOT, env=env,
                        text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(completed.returncode == 0, succeeds, completed.stderr)
                    if not succeeds:
                        self.assertIn('conflicts with WHP_COMPILER_CACHE_CMD', completed.stderr)

    def test_sccache_rejects_conflicting_inherited_compiler_launchers(self):
        runner = BUILD_WRAPPER.read_text(encoding='utf-8')
        prefix, separator, _ = runner.partition(
            '\n. "$script_dir/scripts/whp-build/shell-functions.sh"'
        )
        self.assertTrue(separator)

        with tempfile.TemporaryDirectory() as directory:
            cache = pathlib.Path(directory) / 'sccache'
            cache.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            cache.chmod(0o755)

            for cc, cxx, managed, succeeds in (
                ('ccache cc', 'c++', '0', False),
                ('cc', '/usr/bin/ccache c++', '0', False),
                ('distcc cc', 'c++', '0', False),
                ('sccache cc', 'c++', '0', True),
                ('cc -DNAME=sccache', 'c++', '0', True),
                ('sccache cc', 'c++', '1', False),
                ('cc', 'c++', '1', True),
            ):
                with self.subTest(cc=cc, cxx=cxx, managed=managed):
                    env = {
                        **os.environ,
                        'WHP_BUILD_ENTRY_NORMALIZED': '1',
                        'COMPILER_CACHE': 'sccache',
                        'WHP_COMPILER_CACHE_CMD': str(cache),
                        'WHP_MANAGED_SCCACHE': managed,
                        'CC': cc,
                        'CXX': cxx,
                        'BUILD_DIR': str(pathlib.Path(directory) / 'build'),
                    }
                    script = prefix + (
                        '\nprintf "CC=%s\\nCXX=%s\\n" "$CC" "$CXX"\n'
                    )
                    completed = subprocess.run(
                        ['/bin/sh', '-c', script, str(BUILD_WRAPPER)], cwd=ROOT, env=env,
                        text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(completed.returncode == 0, succeeds,
                                     completed.stderr)
                    if succeeds:
                        self.assertIn('CC=', completed.stdout)
                        if cc == 'cc -DNAME=sccache':
                            self.assertIn('CC=' + str(cache) +
                                          ' cc -DNAME=sccache',
                                          completed.stdout)
                        elif cc == 'sccache cc':
                            self.assertIn('CC=sccache cc', completed.stdout)
                    else:
                        self.assertIn('error:', completed.stderr)

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
        shell = 'set -e; . "$1"; whp_sccache_memory_policy; ' \
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

    def test_sccache_performance_profile_matches_shell_and_ninja(self):
        ninja = load_module(NINJA_BOOTSTRAP, 'whp_ninja_sccache_performance_test')
        policy = ROOT / 'scripts' / 'whp-build' / 'sccache-policy.sh'
        keys = ('SCCACHE_IDLE_TIMEOUT', 'SCCACHE_CACHE_ZSTD_LEVEL',
                'SCCACHE_CLIENT_SIDE', 'SCCACHE_DIRECT', 'SCCACHE_CACHE_SIZE')
        shell = (
            'set -e; . "$1"; whp_sccache_memory_policy; '
            'printf "%s|%s|%s|%s|%s" '
            + ' '.join('"${' + key + '-unset}"' for key in keys)
        )
        for overrides, expected in (
            ({}, ('180', 'unset', 'unset', 'unset', 'unset')),
            ({'WHP_SCCACHE_PROFILE': 'performance'},
             ('600', '1', 'unset', 'unset', 'unset')),
            ({'WHP_SCCACHE_PROFILE': 'performance', 'SCCACHE_IDLE_TIMEOUT': '0',
              'SCCACHE_CACHE_ZSTD_LEVEL': '3', 'SCCACHE_CLIENT_SIDE': '1',
              'SCCACHE_DIRECT': '0', 'SCCACHE_CACHE_SIZE': '12G'},
             ('0', '3', '1', '0', '12G')),
            ({'WHP_SCCACHE_PROFILE': 'performance', 'SCCACHE_CONF': '/custom/config'},
             ('unset', 'unset', 'unset', 'unset', 'unset')),
        ):
            with self.subTest(overrides=overrides):
                run = subprocess.run(
                    ['/bin/sh', '-c', shell, 'sh', str(policy)],
                    env=overrides, text=True, capture_output=True, check=False,
                )
                self.assertEqual(run.returncode, 0, run.stderr)
                self.assertEqual(run.stdout, '|'.join(expected))
                with mock.patch.dict(os.environ, overrides, clear=True):
                    for cache_dir in (None, pathlib.Path('/tmp/whp-sccache')):
                        env = ninja.bootstrap_environment(
                            '/usr/bin/clang++', '', '/opt/bin/sccache', cache_dir,
                        )
                        self.assertEqual(
                            tuple(env.get(key, 'unset') for key in keys), expected,
                        )

        for profile in ('', 'unknown'):
            with self.subTest(profile=profile):
                overrides = {'WHP_SCCACHE_PROFILE': profile}
                run = subprocess.run(
                    ['/bin/sh', '-c', shell, 'sh', str(policy)],
                    env=overrides, text=True, capture_output=True, check=False,
                )
                self.assertNotEqual(run.returncode, 0)
                self.assertIn('WHP_SCCACHE_PROFILE', run.stderr)
                with mock.patch.dict(os.environ, overrides, clear=True):
                    with self.assertRaisesRegex(RuntimeError, 'WHP_SCCACHE_PROFILE'):
                        ninja.bootstrap_environment('/usr/bin/clang++', '', '/opt/bin/sccache')
                    env = ninja.bootstrap_environment('/usr/bin/clang++', '', '/opt/bin/ccache')
                    self.assertNotIn('SCCACHE_CACHE_ZSTD_LEVEL', env)

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

    def test_host_tool_discovery_keeps_artifact_and_build_compilers_separate(self):
        # A cross/remote QEMU compiler and an unrelated cache on PATH must
        # never become the compiler that produces local bootstrap programs.
        prepare = ROOT / 'scripts' / 'whp-build' / 'prepare-build.bash'
        with tempfile.TemporaryDirectory() as directory:
            bin_dir = pathlib.Path(directory)
            fake_cache = bin_dir / 'ccache'
            fake_cache.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            fake_cache.chmod(0o755)
            script = (
                'set -e; source "$1"; whp_prepare_host_tools; '
                'printf "%s|%s|%s|%s|%s" "$CC" "$CXX" '
                '"$CC_FOR_BUILD" "$CXX_FOR_BUILD" "$OBJC_FOR_BUILD"'
            )
            for choice in ('none', 'auto', 'sccache'):
                with self.subTest(policy=choice):
                    env = {
                        **os.environ, 'SOURCE_DIR': str(ROOT),
                        'HOST_OS': 'Linux', 'CC': 'qemu-cross-cc',
                        'CXX': 'qemu-cross-cxx', 'OBJC': 'qemu-cross-objc',
                        'COMPILER_CACHE': choice,
                        'CC_FOR_BUILD': '', 'CXX_FOR_BUILD': '',
                        'OBJC_FOR_BUILD': '',
                        'PATH': str(bin_dir) + os.pathsep + os.environ.get('PATH', ''),
                    }
                    run = subprocess.run(
                        ['bash', '-c', script, 'bash', str(prepare)],
                        env=env, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(run.returncode, 0, run.stderr)
                    self.assertEqual(
                        run.stdout, 'qemu-cross-cc|qemu-cross-cxx|cc|c++|cc'
                    )
                    env.update(CC_FOR_BUILD='build-cc',
                               CXX_FOR_BUILD='build-cxx',
                               OBJC_FOR_BUILD='build-objc')
                    explicit = subprocess.run(
                        ['bash', '-c', script, 'bash', str(prepare)],
                        env=env, text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(explicit.returncode, 0, explicit.stderr)
                    self.assertEqual(
                        explicit.stdout,
                        'qemu-cross-cc|qemu-cross-cxx|build-cc|build-cxx|build-objc',
                    )

    def test_cache_launcher_does_not_relabel_artifact_compilers(self):
        runner = BUILD_WRAPPER.read_text(encoding='utf-8')
        prefix, separator, _ = runner.partition(
            '\n. "$script_dir/scripts/whp-build/shell-functions.sh"'
        )
        self.assertTrue(separator)
        with tempfile.TemporaryDirectory() as directory:
            cache = pathlib.Path(directory) / 'sccache'
            cache.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            cache.chmod(0o755)
            script = prefix + (
                '\nprintf "%s|%s|%s|%s" "$CC" "$CXX" '
                '"$CC_FOR_BUILD" "$CXX_FOR_BUILD"\n'
            )
            for explicit in (False, True):
                with self.subTest(explicit=explicit):
                    env = {
                        **os.environ, 'WHP_BUILD_ENTRY_NORMALIZED': '1',
                        'COMPILER_CACHE': 'sccache',
                        'WHP_COMPILER_CACHE_CMD': str(cache),
                        'CC': 'qemu-cross-cc', 'CXX': 'qemu-cross-cxx',
                        'CC_FOR_BUILD': 'build-cc' if explicit else '',
                        'CXX_FOR_BUILD': 'build-cxx' if explicit else '',
                        'BUILD_DIR': str(pathlib.Path(directory) / 'build'),
                    }
                    result = subprocess.run(
                        ['/bin/sh', '-c', script, str(BUILD_WRAPPER)], cwd=ROOT, env=env,
                        text=True, capture_output=True, check=False,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
                    expected = '|'.join((
                        str(cache) + ' qemu-cross-cc',
                        str(cache) + ' qemu-cross-cxx',
                        'build-cc' if explicit else 'cc',
                        'build-cxx' if explicit else 'c++',
                    ))
                    self.assertEqual(result.stdout, expected)

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
