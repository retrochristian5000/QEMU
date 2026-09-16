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


if __name__ == '__main__':
    unittest.main()
