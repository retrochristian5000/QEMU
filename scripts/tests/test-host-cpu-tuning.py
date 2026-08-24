#!/usr/bin/env python3
import importlib.util
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TOOL = ROOT / 'scripts' / 'whp-build' / 'host-cpu-tuning.py'
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
sys.path.insert(0, str(CONFIG_DIR))

spec = importlib.util.spec_from_file_location('host_cpu_tuning', TOOL)
mod = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(mod)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class HostCpuTuningTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.compiler = pathlib.Path(self.tmp.name) / 'fake-cc'
        self.compiler.write_text(
            '#!/bin/sh\n'
            'for arg in "$@"; do\n'
            '  case "$arg" in\n'
            '    -mcpu=reject|-march=reject|-mtune=reject) exit 1 ;;\n'
            '  esac\n'
            'done\n'
            'exit 0\n',
            encoding='utf-8',
        )
        self.compiler.chmod(0o755)
        self.cc = str(self.compiler)

    def resolve(self, value, arch):
        return mod.resolve_cpu_tuning(value, arch, self.cc, self.cc, self.cc)

    def test_arm64_native_prefers_mcpu(self):
        self.assertEqual(self.resolve('native', 'arm64'), ['-mcpu=native'])

    def test_x86_native_uses_march_and_mtune(self):
        self.assertEqual(
            self.resolve('native', 'x86_64'),
            ['-march=native', '-mtune=native'],
        )

    def test_portable_adds_no_cpu_flags(self):
        self.assertEqual(self.resolve('portable', 'arm64'), [])

    def test_custom_cpu_flags_preserve_user_order(self):
        self.assertEqual(
            self.resolve('-mcpu=apple-m2 -mtune=apple-m2', 'arm64'),
            ['-mcpu=apple-m2', '-mtune=apple-m2'],
        )

    def test_rejects_non_cpu_codegen_flags(self):
        with self.assertRaisesRegex(ValueError, 'only -march='):
            self.resolve('-O3', 'arm64')

    def test_rejects_flags_the_compiler_does_not_support(self):
        with self.assertRaisesRegex(ValueError, 'reject CPU tuning'):
            self.resolve('-mcpu=reject', 'arm64')


class HostCpuTuningConfigTests(unittest.TestCase):
    def test_menu_default_is_editable_native_string(self):
        config = load_module(CONFIG_TOOL, 'whp_host_cpu_config')
        menu = load_module(MENU_TOOL, 'whp_host_cpu_menu')
        option = config.OPTION_BY_KEY['QEMU_HOST_CPU_TUNING']
        self.assertEqual(option.section, 'Host features')
        self.assertEqual(option.kind, 'string')
        self.assertEqual(option.default, 'native')
        self.assertEqual(menu.display_value(option.kind, option.default), 'native')

    def test_custom_tuning_is_exported_verbatim(self):
        config = load_module(CONFIG_TOOL, 'whp_host_cpu_config_export')
        values = config.default_values()
        values['QEMU_HOST_CPU_TUNING'] = '-mcpu=apple-m2 -mtune=apple-m2'
        assignments = config.shell_assignments(config.ConfigState(values), {})
        self.assertIn(
            "QEMU_HOST_CPU_TUNING='-mcpu=apple-m2 -mtune=apple-m2'",
            assignments,
        )


if __name__ == '__main__':
    unittest.main()
