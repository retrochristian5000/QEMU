#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'ensure-ninja.py'


def load_bootstrap_module():
    spec = importlib.util.spec_from_file_location('whp_ensure_ninja_test', BOOTSTRAP)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class NinjaMacOSHostCompilerTests(unittest.TestCase):
    def test_darwin_ignores_target_cxx_when_build_cxx_is_unset(self):
        mod = load_bootstrap_module()

        def fake_which(name: str):
            if name == 'xcrun':
                return '/usr/bin/xcrun'
            return None

        with mock.patch.dict(os.environ, {'CXX': '/tmp/target-clang++'}, clear=True), \
             mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.shutil, 'which', side_effect=fake_which), \
             mock.patch.object(mod, 'run_text', return_value='/usr/bin/clang++'):
            self.assertEqual(mod.select_host_cxx(), '/usr/bin/clang++')

    def test_explicit_build_cxx_remains_authoritative_on_darwin(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(
            os.environ,
            {'CXX_FOR_BUILD': '/opt/host-clang++', 'CXX': '/tmp/target-clang++'},
            clear=True,
        ), mock.patch.object(mod.platform, 'system', return_value='Darwin'):
            self.assertEqual(mod.select_host_cxx(), '/opt/host-clang++')

    def test_darwin_sdkroot_comes_from_xcrun(self):
        mod = load_bootstrap_module()
        with mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.shutil, 'which', return_value='/usr/bin/xcrun'), \
             mock.patch.object(mod, 'run_text', return_value='/SDKs/MacOSX.sdk') as run_text:
            self.assertEqual(mod.select_host_sdkroot(), '/SDKs/MacOSX.sdk')
            run_text.assert_called_once_with(
                ['xcrun', '--sdk', 'macosx', '--show-sdk-path']
            )

    def test_arm64_macos_auto_prefers_arm64e_when_link_probe_succeeds(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
             mock.patch.object(mod, 'compiler_supports_macos_arch', return_value=True) as probe:
            self.assertEqual(
                mod.select_host_macos_arch('/usr/bin/clang++', '/SDKs/MacOSX.sdk'),
                'arm64e',
            )
            probe.assert_called_once_with(
                '/usr/bin/clang++', '/SDKs/MacOSX.sdk', 'arm64e'
            )

    def test_arm64_macos_auto_falls_back_when_arm64e_probe_fails(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(os.environ, {}, clear=True), \
             mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
             mock.patch.object(mod, 'compiler_supports_macos_arch', return_value=False):
            self.assertEqual(
                mod.select_host_macos_arch('/usr/bin/clang++', '/SDKs/MacOSX.sdk'),
                'arm64',
            )

    def test_explicit_arm64e_requires_successful_probe(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(os.environ, {'NINJA_MACOS_ARCH': 'arm64e'}, clear=True), \
             mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
             mock.patch.object(mod, 'compiler_supports_macos_arch', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'arm64e'):
                mod.select_host_macos_arch('/usr/bin/clang++', '/SDKs/MacOSX.sdk')

    def test_bootstrap_environment_replaces_target_sdk_flags(self):
        mod = load_bootstrap_module()
        with mock.patch.dict(
            os.environ,
            {
                'CXX': '/tmp/target-clang++',
                'CXXFLAGS': '--target=aarch64-apple-darwin',
                'LDFLAGS': '--target=aarch64-apple-darwin',
                'SDKROOT': '/wrong-sdk',
                'AR_FOR_BUILD': '/usr/bin/ar',
            },
            clear=True,
        ), mock.patch.object(mod.platform, 'system', return_value='Darwin'):
            env = mod.bootstrap_environment(
                '/usr/bin/clang++', '/SDKs/MacOSX.sdk', macos_arch='arm64e'
            )

        self.assertEqual(env['CXX'], '/usr/bin/clang++')
        self.assertEqual(env['SDKROOT'], '/SDKs/MacOSX.sdk')
        self.assertEqual(
            env['CXXFLAGS'],
            '-arch arm64e -isysroot /SDKs/MacOSX.sdk',
        )
        self.assertEqual(
            env['LDFLAGS'],
            '-arch arm64e -isysroot /SDKs/MacOSX.sdk -Wl,-O2 -Wl,-dead_strip',
        )
        self.assertEqual(env['AR'], '/usr/bin/ar')
        self.assertNotIn('--target=aarch64-apple-darwin', env['CXXFLAGS'])
        self.assertNotIn('--target=aarch64-apple-darwin', env['LDFLAGS'])
        self.assertNotIn('-Wl,-dead_strip', env['CXXFLAGS'])

    def test_marker_records_selected_macos_architecture(self):
        mod = load_bootstrap_module()
        with mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
             mock.patch.object(mod.sys, 'executable', '/usr/bin/python3'):
            marker = mod.marker_text(
                'revision', '/usr/bin/clang++', 'clang version',
                '/SDKs/MacOSX.sdk', 'arm64e'
            )
        self.assertIn('NINJA_MACOS_ARCH=arm64e\n', marker)


    def test_arm64e_probe_requires_pointer_auth_and_executable_slice(self):
        mod = load_bootstrap_module()
        source_seen = []

        def compile_probe(command, **kwargs):
            source_seen.append(kwargs['input'])
            pathlib.Path(command[command.index('-o') + 1]).write_bytes(b'probe')
            return mock.Mock(returncode=0)

        with mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
             mock.patch.object(mod.subprocess, 'run', side_effect=compile_probe), \
             mock.patch.object(mod, 'binary_has_macos_arch', return_value=True) as check_slice, \
             mock.patch.object(mod, 'binary_is_usable', return_value=True) as run:
            self.assertTrue(mod.compiler_supports_macos_arch(
                '/usr/bin/clang++', '/SDKs/MacOSX.sdk', 'arm64e'))
            check_slice.assert_called_once()
            self.assertEqual(check_slice.call_args.args[1], 'arm64e')
            run.assert_called_once()
            self.assertIn('__arm64e__', source_seen[0])
            self.assertIn('__PTRAUTH__', source_seen[0])
            self.assertIn('__has_feature(ptrauth_calls)', source_seen[0])
            self.assertIn('int (*volatile callback)(void)', source_seen[0])

            # A successful link is not sufficient if lipo sees an arm64
            # slice or if macOS cannot launch this exact binary.
            with mock.patch.object(mod, 'binary_has_macos_arch',
                                   return_value=False):
                self.assertFalse(mod.compiler_supports_macos_arch(
                    '/usr/bin/clang++', '/SDKs/MacOSX.sdk', 'arm64e'))
            with mock.patch.object(mod, 'binary_is_usable', return_value=False):
                self.assertFalse(mod.compiler_supports_macos_arch(
                    '/usr/bin/clang++', '/SDKs/MacOSX.sdk', 'arm64e'))

    def test_cached_auto_arm64e_requires_current_marker_slice_and_runtime(self):
        import tempfile

        mod = load_bootstrap_module()
        with tempfile.TemporaryDirectory(prefix='whp-ninja-cache-test-') as tmp:
            binary = pathlib.Path(tmp) / 'ninja'
            marker = pathlib.Path(tmp) / '.whp-ninja-tool'
            binary.write_bytes(b'cached')
            marker.write_text('expected', encoding='utf-8')

            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
                 mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
                 mock.patch.object(mod, 'binary_has_macos_arch', return_value=True) as arch, \
                 mock.patch.object(mod, 'binary_is_usable', return_value=True) as run:
                self.assertTrue(mod.cached_auto_arm64e_ninja(
                    binary, marker, 'expected'))
                arch.assert_called_once_with(binary, 'arm64e')
                run.assert_called_once_with(binary)

                marker.write_text('stale', encoding='utf-8')
                self.assertFalse(mod.cached_auto_arm64e_ninja(
                    binary, marker, 'expected'))
                marker.write_text('expected', encoding='utf-8')

                with mock.patch.object(mod, 'binary_has_macos_arch',
                                       return_value=False):
                    self.assertFalse(mod.cached_auto_arm64e_ninja(
                        binary, marker, 'expected'))
                with mock.patch.object(mod, 'binary_is_usable',
                                       return_value=False):
                    self.assertFalse(mod.cached_auto_arm64e_ninja(
                        binary, marker, 'expected'))
                with mock.patch.dict(os.environ, {'NINJA_MACOS_ARCH': 'arm64'}):
                    self.assertFalse(mod.cached_auto_arm64e_ninja(
                        binary, marker, 'expected'))
                with mock.patch.dict(os.environ, {'NINJA_MACOS_ARCH': 'arm64e'}):
                    self.assertFalse(mod.cached_auto_arm64e_ninja(
                        binary, marker, 'expected'))
                with mock.patch.object(mod.platform, 'machine', return_value='x86_64'):
                    self.assertFalse(mod.cached_auto_arm64e_ninja(
                        binary, marker, 'expected'))

    def test_valid_cached_arm64e_skips_compiler_link_probe(self):
        import tempfile

        mod = load_bootstrap_module()
        with tempfile.TemporaryDirectory(prefix='whp-ninja-cache-test-') as tmp:
            build = pathlib.Path(tmp) / 'qemu-build'
            installation = pathlib.Path(tmp) / '.whp-host-tools' / 'ninja-darwin-arm64'
            installation.mkdir(parents=True)
            binary = installation / 'ninja'
            binary.write_bytes(b'cached')

            with mock.patch.dict(os.environ, {}, clear=True), \
                 mock.patch.object(mod.platform, 'system', return_value='Darwin'), \
                 mock.patch.object(mod.platform, 'machine', return_value='arm64'), \
                 mock.patch.object(mod, 'ensure_ninja_source', return_value='revision'), \
                 mock.patch.object(mod, 'select_host_cxx', return_value='/usr/bin/clang++'), \
                 mock.patch.object(mod, 'select_host_sdkroot', return_value='/SDKs/MacOSX.sdk'), \
                 mock.patch.object(mod, 'select_compiler_cache', return_value=''), \
                 mock.patch.object(mod, 'compiler_version', return_value='clang version'), \
                 mock.patch.object(mod, 'binary_has_macos_arch', return_value=True), \
                 mock.patch.object(mod, 'binary_is_usable', return_value=True), \
                 mock.patch.object(mod, 'select_host_macos_arch') as arch_probe:
                expected = mod.marker_text(
                    'revision', '/usr/bin/clang++', 'clang version',
                    '/SDKs/MacOSX.sdk', 'arm64e')
                (installation / '.whp-ninja-tool').write_text(
                    expected, encoding='utf-8')
                self.assertEqual(mod.ensure_bundled_ninja(build), binary.resolve())
                arch_probe.assert_not_called()


if __name__ == '__main__':
    unittest.main()
