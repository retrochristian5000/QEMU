#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
MENU_TOOL = ROOT / 'scripts' / 'whp-config' / 'menuconfig.py'
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
sys.path.insert(0, str(CONFIG_DIR))


def load_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_menu_module():
    spec = importlib.util.spec_from_file_location('whp_menuconfig', MENU_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WhpConfigTests(unittest.TestCase):
    def test_defaults_are_portable_policy(self):
        mod = load_module()
        values = mod.default_values()
        self.assertEqual(values['QEMU_TARGET_LIST'], 'ppc-softmmu')
        self.assertEqual(values['QEMU_HOST_LTO'], 'auto')
        self.assertEqual(values['PREFIX'], 'auto')
        self.assertEqual(values['MACOS_ENABLE_COCOA'], 'y')
        self.assertEqual(values['MACOS_ENABLE_COREAUDIO'], 'y')
        self.assertEqual(values['BUILD_OPENBIOS'], 'y')
        self.assertEqual(values['CONFIG_MAC_NEWWORLD'], 'y')
        self.assertEqual(values['CONFIG_MAC_OLDWORLD'], 'y')

    def test_load_preserves_unknown_entries_but_does_not_apply_them(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text('WHP_CONFIG_VERSION=1\nBUILD_OPENBIOS=n\nFUTURE_SETTING=keep-me\n', encoding='utf-8')
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_OPENBIOS'], 'n')
            self.assertEqual(loaded.unknown['FUTURE_SETTING'], 'keep-me')

    def test_shell_output_maps_portable_values_and_respects_environment_override(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\n'
                'PREFIX=/opt/whp-qemu\n'
                'MACOS_ENABLE_COCOA=n\n'
                'MACOS_ENABLE_COREAUDIO=n\n'
                'BUILD_OPENBIOS=n\n'
                'QEMU_HOST_LTO=y\n'
                'WHP_INCREMENTAL_BUILD=n\n',
                encoding='utf-8',
            )
            env = os.environ.copy()
            env['BUILD_OPENBIOS'] = '1'
            result = subprocess.run(
                ['python3', str(CONFIG_TOOL), '--shell', str(path)],
                text=True, capture_output=True, check=True, env=env,
            )
            self.assertNotIn('BUILD_OPENBIOS=', result.stdout)
            self.assertIn("PREFIX='/opt/whp-qemu'", result.stdout)
            self.assertIn("MACOS_ENABLE_COCOA='0'", result.stdout)
            self.assertIn("MACOS_ENABLE_COREAUDIO='0'", result.stdout)
            self.assertIn("QEMU_HOST_LTO='1'", result.stdout)
            self.assertIn("WHP_INCREMENTAL_BUILD='0'", result.stdout)

    def test_auto_value_is_not_exported(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\nQEMU_HOST_LTO=auto\nPREFIX=auto\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                ['python3', str(CONFIG_TOOL), '--shell', str(path)],
                text=True, capture_output=True, check=True, env={},
            )
            self.assertNotIn('QEMU_HOST_LTO=', result.stdout)
            self.assertNotIn('PREFIX=', result.stdout)

    def test_device_config_keeps_repository_defaults_before_user_overrides(self):
        mod = load_module()
        values = mod.default_values()
        base = '# repository defaults\nCONFIG_TEST_DEVICES=n\n'
        text = mod.render_ppc_device_config(values, base)
        self.assertTrue(text.startswith(base))
        self.assertLess(text.index('CONFIG_TEST_DEVICES=n'), text.index('CONFIG_MAC_NEWWORLD=y'))

    def test_device_config_replaces_conflicting_repository_machine_assignments(self):
        mod = load_module()
        values = mod.default_values()
        base = 'CONFIG_MAC_NEWWORLD=n\nCONFIG_MAC_OLDWORLD=n\nCONFIG_TEST_DEVICES=n\n'
        text = mod.render_ppc_device_config(values, base)
        self.assertEqual(text.count('CONFIG_MAC_NEWWORLD='), 1)
        self.assertEqual(text.count('CONFIG_MAC_OLDWORLD='), 1)
        self.assertIn('CONFIG_MAC_NEWWORLD=y', text)
        self.assertIn('CONFIG_MAC_OLDWORLD=y', text)
        self.assertIn('CONFIG_TEST_DEVICES=n', text)

    def test_device_config_contains_ppc_machine_overrides(self):
        mod = load_module()
        values = mod.default_values()
        values['CONFIG_MAC_NEWWORLD'] = 'n'
        text = mod.render_ppc_device_config(values, '')
        self.assertIn('CONFIG_MAC_NEWWORLD=n', text)
        self.assertIn('CONFIG_MAC_OLDWORLD=y', text)

    def test_menu_bool_and_choice_cycles(self):
        mod = load_menu_module()
        self.assertEqual(mod.cycle_value('bool', 'y', ()), 'n')
        self.assertEqual(mod.cycle_value('bool', 'n', ()), 'y')
        choices = ('auto', 'y', 'n')
        self.assertEqual(mod.cycle_value('choice', 'auto', choices), 'y')
        self.assertEqual(mod.cycle_value('choice', 'n', choices), 'auto')

    def test_menu_display_values(self):
        mod = load_menu_module()
        self.assertEqual(mod.display_value('bool', 'y'), '[*]')
        self.assertEqual(mod.display_value('bool', 'n'), '[ ]')
        self.assertEqual(mod.display_value('choice', 'auto'), '<auto>')

    def test_save_is_atomic_and_preserves_unknown_entries(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            loaded = mod.ConfigState(mod.default_values(), {'REMOVED_SETTING': 'old'})
            loaded.values['BUILD_OPENBIOS'] = 'n'
            mod.save_config(path, loaded)
            text = path.read_text(encoding='utf-8')
            self.assertIn('WHP_CONFIG_VERSION=1\n', text)
            self.assertIn('BUILD_OPENBIOS=n\n', text)
            self.assertIn('REMOVED_SETTING=old\n', text)
            self.assertFalse((path.parent / '.whpconfig.tmp').exists())


if __name__ == '__main__':
    unittest.main()
