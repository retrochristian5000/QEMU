#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
PORTABLE_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
sys.path.insert(0, str(CONFIG_DIR))


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class MoldConfigTests(unittest.TestCase):
    def test_host_linker_is_selectable_across_os(self):
        config = load_module(CONFIG_TOOL, 'whp_linker_config')
        option = config.OPTION_BY_KEY['QEMU_HOST_LINKER']
        self.assertEqual(option.section, 'Host features')
        self.assertEqual(option.default, 'auto')
        self.assertEqual(option.choices, ('auto', 'system', 'lld', 'mold'))
        values = config.default_values()
        for linker in ('system', 'lld', 'mold'):
            values['QEMU_HOST_LINKER'] = linker
            output = config.shell_assignments(config.ConfigState(values), {})
            self.assertIn(f"QEMU_HOST_LINKER='{linker}'", output)

    def test_portable_system_does_not_inject_linker_flags(self):
        portable = load_module(PORTABLE_TOOL, 'portable_host_system')
        flags = []
        with patch.dict(os.environ, {'LDFLAGS': '', 'CC': 'cc', 'CXX': 'c++'}):
            portable.add_portable_host_linker(
                {'QEMU_HOST_LINKER': 'system', 'BOOTSTRAP_MOLD': 'auto'}, flags,
            )
        self.assertEqual(flags, [])

    def test_portable_rejects_conflicting_linker_overrides(self):
        portable = load_module(PORTABLE_TOOL, 'portable_host_conflict')
        flags = []
        with patch.dict(os.environ, {'LDFLAGS': '-fuse-ld=lld'}):
            with self.assertRaisesRegex(RuntimeError, 'conflicts with LDFLAGS'):
                portable.add_portable_host_linker(
                    {'QEMU_HOST_LINKER': 'system', 'BOOTSTRAP_MOLD': 'auto'},
                    flags,
                )
        self.assertEqual(flags, [])

    def test_portable_linker_probes_both_compilers(self):
        portable = load_module(PORTABLE_TOOL, 'portable_host_lld')
        with tempfile.TemporaryDirectory() as td:
            fake = pathlib.Path(td) / 'fake-compiler'
            log = pathlib.Path(td) / 'calls'
            fake.write_text(
                '#!/usr/bin/env python3\n'
                'import os, pathlib, sys\n'
                'args = sys.argv[1:]\n'
                'assert "-fuse-ld=lld" in args\n'
                'with open(os.environ["WHP_FAKE_LINK_LOG"], "a") as stream:\n'
                '    stream.write(" ".join(args) + "\\n")\n'
                'output = pathlib.Path(args[args.index("-o") + 1])\n'
                'output.write_text("#!/usr/bin/env python3\\n")\n'
                'output.chmod(0o755)\n',
                encoding='utf-8',
            )
            fake.chmod(0o755)
            flags = []
            with patch.dict(os.environ, {
                'CC': str(fake), 'CXX': str(fake), 'LDFLAGS': '',
                'WHP_FAKE_LINK_LOG': str(log),
            }):
                portable.add_portable_host_linker(
                    {'QEMU_HOST_LINKER': 'lld', 'BOOTSTRAP_MOLD': 'auto'}, flags,
                )
            self.assertEqual(flags, ['--extra-ldflags=-fuse-ld=lld'])
            self.assertEqual(len(log.read_text().splitlines()), 2)

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
