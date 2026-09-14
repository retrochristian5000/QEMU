#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
sys.path.insert(0, str(CONFIG_DIR))


def load_module(path: pathlib.Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class WhpHardwareMenuTests(unittest.TestCase):
    def test_audio_devices_live_under_generic_hardware_section(self):
        config = load_module(CONFIG_TOOL, 'whp_config_hardware')
        for key in (
            'I386_AUDIO_SB16',
            'I386_AUDIO_ADLIB',
            'I386_AUDIO_GUS',
            'I386_AUDIO_CS4231A',
            'I386_AUDIO_PCSPK',
            'I386_AUDIO_ES1370',
            'I386_AUDIO_AC97',
            'I386_AUDIO_CS4630',
            'I386_AUDIO_HDA',
        ):
            self.assertEqual(config.OPTION_BY_KEY[key].section, 'QEMU hardware')

    def test_es1370_groups_i386_and_ppc_target_choices(self):
        config = load_module(CONFIG_TOOL, 'whp_config_es1370_targets')
        self.assertIn('PPC_AUDIO_ES1370', config.OPTION_BY_KEY)
        i386 = config.OPTION_BY_KEY['I386_AUDIO_ES1370']
        ppc = config.OPTION_BY_KEY['PPC_AUDIO_ES1370']
        self.assertTrue(hasattr(i386, 'group'))
        self.assertEqual(i386.group, 'Ensoniq ES1370 (PCI)')
        self.assertEqual(ppc.group, i386.group)
        self.assertEqual(i386.label, 'i386')
        self.assertEqual(ppc.label, 'ppc')
        for option in (i386, ppc):
            self.assertEqual(option.kind, 'choice')
            self.assertEqual(option.default, 'auto')
            self.assertEqual(option.choices, ('auto', 'y', 'n'))

    def test_menu_dump_shows_one_es1370_group_with_two_targets(self):
        with tempfile.TemporaryDirectory() as td:
            config_path = pathlib.Path(td) / '.whpconfig'
            config_path.write_text(
                'WHP_CONFIG_VERSION=2\n'
                'I386_AUDIO_ES1370=n\n'
                'PPC_AUDIO_ES1370=y\n',
                encoding='utf-8',
            )
            result = subprocess.run(
                [sys.executable, str(MENU_TOOL), str(config_path), '--dump'],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertIn('QEMU hardware', result.stdout)
        self.assertEqual(result.stdout.count('Ensoniq ES1370 (PCI)'), 1)
        self.assertIn('<n>        i386', result.stdout)
        self.assertIn('<y>        ppc', result.stdout)


if __name__ == '__main__':
    unittest.main()
