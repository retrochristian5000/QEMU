#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
import importlib.util
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
MENU_TOOL = ROOT / 'scripts' / 'whp-config' / 'menuconfig.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
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


def load_portable_build_module():
    spec = importlib.util.spec_from_file_location('whp_portable_build', PORTABLE_BUILD_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WhpConfigTests(unittest.TestCase):
    def test_defaults_are_portable_policy(self):
        mod = load_module()
        values = mod.default_values()
        self.assertEqual(values['QEMU_HOST_LTO'], 'auto')
        self.assertEqual(values['PREFIX'], 'auto')
        self.assertEqual(values['MACOS_ENABLE_COCOA'], 'auto')
        self.assertEqual(values['MACOS_ENABLE_COREAUDIO'], 'auto')
        self.assertEqual(values['MACOS_ENABLE_GTK'], 'auto')
        self.assertEqual(values['MACOS_ENABLE_PA'], 'auto')
        self.assertEqual(values['BUILD_OPENBIOS'], 'auto')
        self.assertEqual(values['BOOTSTRAP_POWERPC_TOOLCHAIN'], 'auto')
        self.assertEqual(values['BOOTSTRAP_WIN9X_TOOLCHAIN'], 'n')
        self.assertEqual(values['INSTALL'], 'n')
        self.assertEqual(values['CONFIG_MAC_NEWWORLD'], 'y')
        self.assertEqual(values['CONFIG_MAC_OLDWORLD'], 'y')

    def test_run_tests_is_user_controlled_build_behavior(self):
        mod = load_module()
        option = mod.OPTION_BY_KEY['RUN_TESTS']
        self.assertEqual(option.section, 'Build behavior')
        self.assertEqual(option.label, 'Run tests after build')
        self.assertEqual(option.kind, 'bool')
        self.assertEqual(option.default, 'y')

        values = mod.default_values()
        self.assertEqual(values['RUN_TESTS'], 'y')
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("RUN_TESTS='1'", assignments)

        values['RUN_TESTS'] = 'n'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("RUN_TESTS='0'", assignments)

    def test_portable_test_runner_uses_qemu_make_check(self):
        mod = load_portable_build_module()
        with tempfile.TemporaryDirectory() as td:
            td_path = pathlib.Path(td)
            build_dir = td_path / 'build'
            log = td_path / 'make.log'
            fake_make = td_path / 'gmake'
            fake_make.write_text(
                '#!/bin/sh\n'
                'if [ "${1:-}" = "--version" ]; then\n'
                '  echo "GNU Make 4.4"\n'
                '  exit 0\n'
                'fi\n'
                'printf "%s\\n" "$*" >> "$WHP_TEST_RUNNER_LOG"\n',
                encoding='utf-8',
            )
            fake_make.chmod(0o755)
            with mock.patch.dict(
                os.environ,
                {'MAKE_CMD': str(fake_make), 'WHP_TEST_RUNNER_LOG': str(log)},
                clear=False,
            ):
                mod.run_qemu_tests(build_dir, '3')
            self.assertEqual(
                log.read_text(encoding='utf-8').strip(),
                f'-C {build_dir} -j3 check',
            )

    def test_boolean_defaults_are_valid_and_install_is_opt_in(self):
        mod = load_module()
        values = mod.default_values()
        for option in mod.OPTIONS:
            if option.kind == 'bool':
                self.assertIn(option.default, ('y', 'n'), option.key)
                self.assertEqual(values[option.key], option.default, option.key)
        self.assertEqual(values['INSTALL'], 'n')

    def test_output_defaults_select_img_i386_and_ppc(self):
        mod = load_module()
        values = mod.default_values()
        self.assertEqual(values['BUILD_QEMU_IMG'], 'y')
        self.assertEqual(values['BUILD_QEMU_SYSTEM_I386'], 'y')
        self.assertEqual(values['BUILD_QEMU_SYSTEM_PPC'], 'y')

        assignments = mod.shell_assignments(
            mod.ConfigState(values),
            {},
        )
        self.assertIn("BUILD_QEMU_IMG='1'", assignments)
        self.assertIn("BUILD_QEMU_SYSTEM_I386='1'", assignments)
        self.assertIn("BUILD_QEMU_SYSTEM_PPC='1'", assignments)
        self.assertNotIn('QEMU_TARGET_LIST=', assignments)

    def test_auto_optional_defaults_are_not_forced_into_shell(self):
        mod = load_module()
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        for key in (
            'QEMU_HOST_LTO',
            'MACOS_ENABLE_COCOA',
            'MACOS_ENABLE_COREAUDIO',
            'MACOS_ENABLE_GTK',
            'MACOS_ENABLE_PA',
            'BUILD_OPENBIOS',
            'BOOTSTRAP_POWERPC_TOOLCHAIN',
            'PREFIX',
        ):
            self.assertNotIn(f'{key}=', assignments)
        self.assertIn("BOOTSTRAP_WIN9X_TOOLCHAIN='0'", assignments)
        self.assertIn("INSTALL='0'", assignments)

    def test_win9x_cross_tools_are_separate_and_opt_in(self):
        mod = load_module()
        option = mod.OPTION_BY_KEY['BOOTSTRAP_WIN9X_TOOLCHAIN']
        self.assertEqual(option.section, 'Windows 9x cross-tools')
        self.assertEqual(option.label, 'Bootstrap i386-pc-win9x LLVM toolchain')
        self.assertEqual(option.kind, 'bool')
        self.assertEqual(option.default, 'n')
        self.assertNotEqual(option.section, 'Firmware')
        self.assertIn('Windows 9x cross-tools', [section for section, _ in mod.sections()])

        values = mod.default_values()
        values['BOOTSTRAP_WIN9X_TOOLCHAIN'] = 'y'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("BOOTSTRAP_WIN9X_TOOLCHAIN='1'", assignments)

    def test_device_selection_is_exported_without_boolean_reencoding(self):
        mod = load_module()
        values = mod.default_values()
        values['CONFIG_MAC_OLDWORLD'] = 'n'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("CONFIG_MAC_NEWWORLD='y'", assignments)
        self.assertIn("CONFIG_MAC_OLDWORLD='n'", assignments)

    def test_menu_uses_output_toggles_instead_of_a_raw_target_list(self):
        mod = load_module()
        self.assertNotIn('QEMU_TARGET_LIST', mod.OPTION_BY_KEY)
        self.assertNotIn('Build targets', [section for section, _ in mod.sections()])

    def test_host_feature_labels_are_platform_neutral(self):
        mod = load_module()
        labels = {option.key: option.label for option in mod.OPTIONS}
        self.assertEqual(labels['MACOS_ENABLE_COCOA'], 'Cocoa')
        self.assertEqual(labels['MACOS_ENABLE_COREAUDIO'], 'CoreAudio')
        self.assertEqual(labels['MACOS_ENABLE_GTK'], 'GTK')
        self.assertEqual(labels['MACOS_ENABLE_PA'], 'PulseAudio')

    def test_version_one_config_migrates_without_losing_explicit_values(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\n'
                'BUILD_OPENBIOS=y\n'
                'MACOS_ENABLE_GTK=n\n'
                'INSTALL=y\n',
                encoding='utf-8',
            )
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_OPENBIOS'], 'y')
            self.assertEqual(loaded.values['MACOS_ENABLE_GTK'], 'n')
            self.assertEqual(loaded.values['INSTALL'], 'y')
            self.assertEqual(loaded.values['MACOS_ENABLE_PA'], 'auto')
            self.assertEqual(loaded.values['BOOTSTRAP_WIN9X_TOOLCHAIN'], 'n')

    def test_legacy_target_list_migrates_to_output_toggles(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\n'
                'QEMU_TARGET_LIST=i386-softmmu\n',
                encoding='utf-8',
            )
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_I386'], 'y')
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_PPC'], 'n')
            self.assertNotIn('QEMU_TARGET_LIST', loaded.unknown)
            self.assertNotIn('QEMU_TARGET_LIST=', mod.render_config(loaded))

    def test_explicit_output_toggles_override_legacy_target_list(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\n'
                'QEMU_TARGET_LIST=ppc-softmmu\n'
                'BUILD_QEMU_SYSTEM_I386=y\n'
                'BUILD_QEMU_SYSTEM_PPC=n\n',
                encoding='utf-8',
            )
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_I386'], 'y')
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_PPC'], 'n')

    def test_load_preserves_unknown_entries_but_does_not_apply_them(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text('WHP_CONFIG_VERSION=2\nBUILD_OPENBIOS=n\nFUTURE_SETTING=keep-me\n', encoding='utf-8')
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_OPENBIOS'], 'n')
            self.assertEqual(loaded.unknown['FUTURE_SETTING'], 'keep-me')

    def test_shell_output_maps_portable_values_and_respects_environment_override(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=2\n'
                'PREFIX=/opt/whp-qemu\n'
                'MACOS_ENABLE_COCOA=n\n'
                'MACOS_ENABLE_COREAUDIO=n\n'
                'BUILD_OPENBIOS=n\n'
                'BOOTSTRAP_WIN9X_TOOLCHAIN=y\n'
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
            self.assertIn("BOOTSTRAP_WIN9X_TOOLCHAIN='1'", result.stdout)
            self.assertIn("QEMU_HOST_LTO='1'", result.stdout)
            self.assertIn("WHP_INCREMENTAL_BUILD='0'", result.stdout)

    def test_prefix_allows_spaces_and_remains_shell_quoted(self):
        mod = load_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=2\nPREFIX=C:/Program Files/WHP QEMU\n',
                encoding='utf-8',
            )
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['PREFIX'], 'C:/Program Files/WHP QEMU')
            assignments = mod.shell_assignments(loaded, {})
            self.assertIn("PREFIX='C:/Program Files/WHP QEMU'", assignments)

    def test_auto_value_is_not_exported(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=2\nQEMU_HOST_LTO=auto\nPREFIX=auto\nBUILD_OPENBIOS=auto\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                ['python3', str(CONFIG_TOOL), '--shell', str(path)],
                text=True, capture_output=True, check=True, env={},
            )
            self.assertNotIn('QEMU_HOST_LTO=', result.stdout)
            self.assertNotIn('PREFIX=', result.stdout)
            self.assertNotIn('BUILD_OPENBIOS=', result.stdout)

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
            self.assertIn('WHP_CONFIG_VERSION=2\n', text)
            self.assertIn('BUILD_OPENBIOS=n\n', text)
            self.assertIn('BOOTSTRAP_WIN9X_TOOLCHAIN=n\n', text)
            self.assertIn('REMOVED_SETTING=old\n', text)
            self.assertFalse((path.parent / '.whpconfig.tmp').exists())

    def test_portable_core_probe_omits_auto_optional_dependencies(self):
        env = os.environ.copy()
        env.update({
            'WHP_PORTABLE_PROBE_ONLY': '1',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_QEMU_SYSTEM_I386': '1',
            'BUILD_OPENBIOS': 'auto',
            'MACOS_ENABLE_GTK': 'auto',
            'MACOS_ENABLE_PA': 'auto',
        })
        result = subprocess.run(
            ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-i386'],
            text=True, capture_output=True, check=True, env=env,
        )
        self.assertIn('CONFIGURE_ARG=--target-list=i386-softmmu', result.stdout)
        self.assertNotIn('--enable-gtk', result.stdout)
        self.assertNotIn('--enable-pa', result.stdout)
        self.assertNotIn('OPTIONAL_DECLINE=OpenBIOS', result.stdout)

    def test_portable_core_records_auto_openbios_decline_for_ppc(self):
        env = os.environ.copy()
        env.update({
            'WHP_PORTABLE_PROBE_ONLY': '1',
            'BUILD_QEMU_SYSTEM_PPC': '1',
            'BUILD_QEMU_SYSTEM_I386': '0',
            'BUILD_OPENBIOS': 'auto',
        })
        result = subprocess.run(
            ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-ppc'],
            text=True, capture_output=True, check=True, env=env,
        )
        self.assertIn(
            'OPTIONAL_DECLINE=OpenBIOS:auto:firmware-adapter-unavailable',
            result.stdout,
        )


if __name__ == '__main__':
    unittest.main()
