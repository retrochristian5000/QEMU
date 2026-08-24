#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'


def load_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SeaBiosConfigTests(unittest.TestCase):
    def test_seabios_options_are_firmware_tristates(self):
        mod = load_module()
        build = mod.OPTION_BY_KEY['BUILD_SEABIOS']
        bootstrap = mod.OPTION_BY_KEY['BOOTSTRAP_I386_TOOLCHAIN']
        self.assertEqual(build.section, 'Firmware')
        self.assertEqual(build.kind, 'choice')
        self.assertEqual(build.default, 'auto')
        self.assertEqual(build.choices, ('auto', 'y', 'n'))
        self.assertEqual(bootstrap.section, 'Firmware')
        self.assertEqual(bootstrap.kind, 'choice')
        self.assertEqual(bootstrap.default, 'auto')
        self.assertEqual(bootstrap.choices, ('auto', 'y', 'n'))

    def test_explicit_seabios_settings_export_as_shell_booleans(self):
        mod = load_module()
        values = mod.default_values()
        values['BUILD_SEABIOS'] = 'y'
        values['BOOTSTRAP_I386_TOOLCHAIN'] = 'n'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("BUILD_SEABIOS='1'", assignments)
        self.assertIn("BOOTSTRAP_I386_TOOLCHAIN='0'", assignments)

    def test_auto_seabios_settings_are_not_exported(self):
        mod = load_module()
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        self.assertNotIn('BUILD_SEABIOS=', assignments)
        self.assertNotIn('BOOTSTRAP_I386_TOOLCHAIN=', assignments)

    def test_pc_bios_uses_ata_dma_but_isapc_stays_conservative(self):
        normal = (ROOT / 'roms' / 'config.seabios-256k').read_text(encoding='utf-8')
        isapc = (ROOT / 'roms' / 'config.seabios-128k').read_text(encoding='utf-8')
        self.assertIn('CONFIG_ATA_DMA=y', normal)
        self.assertIn('CONFIG_ATA_DMA=n', isapc)


if __name__ == '__main__':
    unittest.main()
