#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
sys.path.insert(0, str(CONFIG_DIR))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MoldConfigTests(unittest.TestCase):
    def test_mold_bootstrap_is_a_host_feature(self):
        config = load_module(CONFIG_TOOL, 'whp_mold_config')
        option = config.OPTION_BY_KEY['BOOTSTRAP_MOLD']
        self.assertEqual(option.section, 'Host features')
        self.assertEqual(option.default, 'auto')
        self.assertEqual(option.choices, ('auto', 'y', 'n'))

    def test_auto_does_not_force_mold_into_environment(self):
        config = load_module(CONFIG_TOOL, 'whp_mold_config_auto')
        state = config.ConfigState(config.default_values())
        assignments = config.shell_assignments(state, {})
        self.assertNotIn('BOOTSTRAP_MOLD=', assignments)

    def test_explicit_yes_exports_numeric_bootstrap_policy(self):
        config = load_module(CONFIG_TOOL, 'whp_mold_config_yes')
        values = config.default_values()
        values['BOOTSTRAP_MOLD'] = 'y'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertIn("BOOTSTRAP_MOLD='1'", assignments)

    def test_menu_exposes_mold_control(self):
        config = load_module(CONFIG_TOOL, 'whp_mold_config_menu')
        menu = load_module(MENU_TOOL, 'whp_mold_menu')
        values = config.default_values()
        values['BOOTSTRAP_MOLD'] = 'y'
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            config.save_config(path, config.ConfigState(values))
            loaded = config.load_config(path)
            labels = {
                option.key: (option.label, loaded.values[option.key])
                for _, options in config.sections()
                for option in options
            }
            self.assertIn('BOOTSTRAP_MOLD', labels)
            self.assertIn('mold', labels['BOOTSTRAP_MOLD'][0].lower())
            self.assertEqual(
                menu.display_value(
                    config.OPTION_BY_KEY['BOOTSTRAP_MOLD'].kind,
                    labels['BOOTSTRAP_MOLD'][1],
                ),
                '<y>',
            )


if __name__ == '__main__':
    unittest.main()
