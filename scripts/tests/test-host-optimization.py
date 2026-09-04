#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import subprocess
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
BUILDER = ROOT / 'builder.bash'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def portable_probe(optimization: str | None = None) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update({
        'WHP_PORTABLE_PROBE_ONLY': '1',
        'BUILD_QEMU_SYSTEM_PPC': '0',
        'BUILD_QEMU_SYSTEM_I386': '1',
        'BUILD_OPENBIOS': 'auto',
        'MACOS_ENABLE_GTK': 'auto',
        'MACOS_ENABLE_PA': 'auto',
    })
    if optimization is None:
        env.pop('QEMU_HOST_OPTIMIZATION', None)
    else:
        env['QEMU_HOST_OPTIMIZATION'] = optimization
    return subprocess.run(
        ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-i386'],
        text=True,
        capture_output=True,
        check=False,
        env=env,
    )


class HostOptimizationTests(unittest.TestCase):
    def test_default_policy_is_o3_without_ofast(self):
        mod = load_config_module()
        option = mod.OPTION_BY_KEY['QEMU_HOST_OPTIMIZATION']
        self.assertEqual(option.default, '3')
        self.assertEqual(option.choices, ('0', '1', '2', '3', 'g', 's'))
        self.assertNotIn('fast', option.choices)
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        self.assertIn("QEMU_HOST_OPTIMIZATION='3'", assignments)

    def test_portable_core_defaults_to_o3(self):
        result = portable_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONFIGURE_ARG=--extra-cflags=-O3', result.stdout)

    def test_portable_core_preserves_explicit_lower_level(self):
        result = portable_probe('2')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONFIGURE_ARG=--extra-cflags=-O2', result.stdout)
        self.assertNotIn('CONFIGURE_ARG=--extra-cflags=-O3', result.stdout)

    def test_portable_core_rejects_ofast(self):
        result = portable_probe('fast')
        self.assertEqual(result.returncode, 2)
        self.assertIn('QEMU_HOST_OPTIMIZATION must be one of', result.stderr)

    def test_bash_path_applies_optimization_after_firmware_preparation(self):
        builder = BUILDER.read_text(encoding='utf-8')
        firmware_index = builder.index('whp_prepare_mold')
        strip_index = builder.index('whp_strip_inherited_host_performance_overrides')
        optimization_index = builder.index(
            'configure_args+=(--extra-cflags="-O$QEMU_HOST_OPTIMIZATION")'
        )
        configure_index = builder.index('whp_configure_build')

        self.assertLess(firmware_index, strip_index)
        self.assertLess(strip_index, optimization_index)
        self.assertLess(optimization_index, configure_index)
        self.assertIn('0|1|2|3|g|s)', builder)
        self.assertNotIn('-Ofast', builder)


if __name__ == '__main__':
    unittest.main()
