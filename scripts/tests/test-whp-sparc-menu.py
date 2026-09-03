#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_ENTRY = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
BUILDER = ROOT / 'builder.sh'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class SparcMenuTargetTests(unittest.TestCase):
    def test_sparc_is_an_opt_in_build_output(self):
        mod = load_config_module()
        option = mod.OPTION_BY_KEY['BUILD_QEMU_SYSTEM_SPARC']
        self.assertEqual(option.section, 'Build outputs')
        self.assertEqual(option.label, 'qemu-system-sparc')
        self.assertEqual(option.kind, 'bool')
        self.assertEqual(option.default, 'n')

        values = mod.default_values()
        self.assertEqual(values['BUILD_QEMU_SYSTEM_SPARC'], 'n')
        values['BUILD_QEMU_SYSTEM_SPARC'] = 'y'
        assignments = mod.shell_assignments(mod.ConfigState(values), {})
        self.assertIn("BUILD_QEMU_SYSTEM_SPARC='1'", assignments)

    def test_legacy_sparc_target_list_migrates_to_output_toggle(self):
        mod = load_config_module()
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            path.write_text(
                'WHP_CONFIG_VERSION=1\nQEMU_TARGET_LIST=sparc-softmmu\n',
                encoding='utf-8',
            )
            loaded = mod.load_config(path)
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_SPARC'], 'y')
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_I386'], 'n')
            self.assertEqual(loaded.values['BUILD_QEMU_SYSTEM_PPC'], 'n')

    def test_portable_entry_adds_sparc_to_qemu_target_list(self):
        env = os.environ.copy()
        env.update({
            'WHP_PORTABLE_PROBE_ONLY': '1',
            'BUILD_QEMU_IMG': '0',
            'BUILD_QEMU_SYSTEM_I386': '0',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_QEMU_SYSTEM_SPARC': '1',
            'BUILD_OPENBIOS': '0',
            'BOOTSTRAP_POWERPC_TOOLCHAIN': '0',
        })
        result = subprocess.run(
            ['python3', str(PORTABLE_ENTRY)],
            text=True,
            capture_output=True,
            check=True,
            env=env,
        )
        self.assertIn(
            'CONFIGURE_ARG=--target-list=sparc-softmmu',
            result.stdout,
        )

    def test_bash_runner_registers_sparc_before_diagnostics(self):
        text = BUILDER.read_text(encoding='utf-8')
        prepare = text.index('whp_prepare_build "$@"')
        add_sparc = text.index('whp_qemu_target_list_add sparc-softmmu')
        refresh_args = text.index('whp_prepare_configure_args', add_sparc)
        diagnostics = text.index('whp_apply_qemu_diagnostics')
        self.assertLess(prepare, add_sparc)
        self.assertLess(add_sparc, refresh_args)
        self.assertLess(refresh_args, diagnostics)
        self.assertIn(
            'whp_require_boolean_values BUILD_QEMU_SYSTEM_SPARC',
            text,
        )


if __name__ == '__main__':
    unittest.main()
