#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import shlex
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
PORTABLE_BUILD_ENTRY = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
BUILDER = ROOT / 'builder.bash'
PGO_HELPER = ROOT / 'scripts' / 'whp-build' / 'pgo-profile.py'


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
    # Keep the ordinary build aligned with QEMU/Meson's -O2 baseline while
    # retaining explicit -O1/-O3 overrides for fast iteration and validation.
    def test_default_policy_is_o2_without_ofast(self):
        mod = load_config_module()
        option = mod.OPTION_BY_KEY['QEMU_HOST_OPTIMIZATION']
        self.assertEqual(option.default, '2')
        self.assertEqual(option.choices, ('0', '1', '2', '3', 'g', 's'))
        self.assertNotIn('fast', option.choices)
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        self.assertIn("QEMU_HOST_OPTIMIZATION='2'", assignments)

    def test_portable_core_defaults_to_o2(self):
        result = portable_probe()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONFIGURE_ARG=--extra-cflags=-O2', result.stdout)
        self.assertNotIn('CONFIGURE_ARG=--extra-cflags=-O3', result.stdout)

    def test_portable_core_preserves_explicit_higher_level(self):
        result = portable_probe('3')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONFIGURE_ARG=--extra-cflags=-O3', result.stdout)
        self.assertNotIn('CONFIGURE_ARG=--extra-cflags=-O2', result.stdout)

    def test_portable_core_preserves_explicit_lower_level(self):
        result = portable_probe('1')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('CONFIGURE_ARG=--extra-cflags=-O1', result.stdout)
        self.assertNotIn('CONFIGURE_ARG=--extra-cflags=-O2', result.stdout)

    def test_portable_core_rejects_ofast(self):
        result = portable_probe('fast')
        self.assertEqual(result.returncode, 2)
        self.assertIn('QEMU_HOST_OPTIMIZATION must be one of', result.stderr)

    def test_public_portable_entry_rejects_zero_job_parallelism(self):
        env = os.environ.copy()
        env.update({
            'WHP_PORTABLE_PROBE_ONLY': '1',
            'BUILD_QEMU_IMG': '0',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_QEMU_SYSTEM_I386': '1',
            'BUILD_OPENBIOS': 'auto',
            'BOOTSTRAP_POWERPC_TOOLCHAIN': 'auto',
            'BOOTSTRAP_NATIVE_LLVM': '0',
            'JOBS': '0',
        })
        result = subprocess.run(
            ['python3', str(PORTABLE_BUILD_ENTRY), 'qemu-system-i386'],
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
        self.assertEqual(result.returncode, 2, result.stderr)
        self.assertIn('JOBS must be a positive integer', result.stderr)

    def test_portable_lto_mode_controls_meson_and_enablement(self):
        for mode, expected in (
            ('auto', None),
            ('thin', '-Db_lto_mode=thin'),
            ('full', '-Db_lto_mode=default'),
        ):
            with self.subTest(mode=mode):
                env = os.environ.copy()
                env.update({
                    'WHP_PORTABLE_PROBE_ONLY': '1',
                    'BUILD_QEMU_SYSTEM_PPC': '0',
                    'BUILD_QEMU_SYSTEM_I386': '1',
                    'QEMU_HOST_LTO': 'auto',
                    'QEMU_HOST_LTO_MODE': mode,
                })
                proc = subprocess.run(
                    ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-i386'],
                    text=True, capture_output=True, check=False, env=env,
                )
                self.assertEqual(proc.returncode, 0, proc.stderr)
                if expected is None:
                    self.assertNotIn('CONFIGURE_ARG=-Db_lto_mode=', proc.stdout)
                else:
                    self.assertIn('CONFIGURE_ARG=--enable-lto', proc.stdout)
                    self.assertIn('CONFIGURE_ARG=' + expected, proc.stdout)
                if mode == 'full':
                    self.assertIn('CONFIGURE_ARG=-Db_thinlto_cache=false',
                                  proc.stdout)

    def test_portable_lto_mode_rejects_disabled_or_invalid_settings(self):
        for mode, enabled, error in (
            ('thin', 'n', 'conflicts with disabled QEMU_HOST_LTO'),
            ('full', 'n', 'conflicts with disabled QEMU_HOST_LTO'),
            ('invalid', 'auto', 'QEMU_HOST_LTO_MODE must be one of'),
        ):
            with self.subTest(mode=mode, enabled=enabled):
                env = os.environ.copy()
                env.update({
                    'WHP_PORTABLE_PROBE_ONLY': '1',
                    'BUILD_QEMU_SYSTEM_PPC': '0',
                    'BUILD_QEMU_SYSTEM_I386': '1',
                    'QEMU_HOST_LTO': enabled,
                    'QEMU_HOST_LTO_MODE': mode,
                })
                proc = subprocess.run(
                    ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-i386'],
                    text=True, capture_output=True, check=False, env=env,
                )
                self.assertEqual(proc.returncode, 2)
                self.assertIn(error, proc.stderr)

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
        self.assertIn('QEMU_HOST_OPTIMIZATION="${QEMU_HOST_OPTIMIZATION:-2}"', builder)
        self.assertIn('0|1|2|3|g|s)', builder)
        self.assertNotIn('-Ofast', builder)


    def test_pgo_configuration_is_opt_in_and_matches_menu(self):
        mod = load_config_module()
        option = mod.OPTION_BY_KEY['QEMU_HOST_PGO']
        self.assertEqual(option.default, 'off')
        self.assertEqual(option.choices, ('off', 'generate', 'use'))
        fallback = (ROOT / 'scripts' / 'whp-config' / 'menu-options.def').read_text(
            encoding='utf-8')
        self.assertIn(
            'QEMU_HOST_PGO|Host features|QEMU host profile-guided optimization|'
            'choice|off|off,generate,use|', fallback)
        assignments = mod.shell_assignments(mod.ConfigState(mod.default_values()), {})
        self.assertIn("QEMU_HOST_PGO='off'", assignments)

    def test_portable_pgo_modes_and_invalid_override(self):
        for mode in ('off', 'generate', 'use', 'invalid'):
            with self.subTest(mode=mode):
                env = os.environ.copy()
                env.update({
                    'WHP_PORTABLE_PROBE_ONLY': '1',
                    'BUILD_QEMU_SYSTEM_PPC': '0',
                    'BUILD_QEMU_SYSTEM_I386': '1',
                    'QEMU_HOST_PGO': mode,
                })
                proc = subprocess.run(
                    ['python3', str(PORTABLE_BUILD_TOOL), 'qemu-system-i386'],
                    text=True, capture_output=True, check=False, env=env,
                )
                if mode == 'invalid':
                    self.assertEqual(proc.returncode, 2)
                    self.assertIn('QEMU_HOST_PGO must be one of:', proc.stderr)
                else:
                    self.assertEqual(proc.returncode, 0, proc.stderr)
                    self.assertIn('CONFIGURE_ARG=-Db_pgo=' + mode, proc.stdout)

    def test_bash_pgo_is_meson_only_with_strict_validation(self):
        prepare = (ROOT / 'scripts' / 'whp-build' / 'prepare-build.bash').read_text(
            encoding='utf-8')
        self.assertIn('QEMU_HOST_PGO="${QEMU_HOST_PGO:-off}"', prepare)
        self.assertIn('off|generate|use)', prepare)
        self.assertIn('configure_args+=("-Db_pgo=$QEMU_HOST_PGO")', prepare)
        self.assertNotIn('CFLAGS="-fprofile-', prepare)


    def test_pgo_use_requires_profiles_not_just_a_tool(self):
        with tempfile.TemporaryDirectory() as temp:
            proc = subprocess.run(
                [sys.executable, str(PGO_HELPER), '--build-dir', temp],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 2)
            self.assertIn('QEMU_HOST_PGO=use requires actual training data',
                          proc.stderr)

    def test_pgo_use_reuses_existing_indexed_profile(self):
        with tempfile.TemporaryDirectory() as temp:
            indexed = pathlib.Path(temp) / 'default.profdata'
            indexed.write_bytes(b'nonempty test fixture')
            proc = subprocess.run(
                [sys.executable, str(PGO_HELPER), '--build-dir', temp],
                text=True, capture_output=True, check=False,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('using existing indexed profile', proc.stdout)

    def test_pgo_use_auto_merges_when_raw_profile_is_present(self):
        with tempfile.TemporaryDirectory() as temp:
            build_dir = pathlib.Path(temp)
            raw_dir = build_dir / 'pgo-raw'
            raw_dir.mkdir()
            (raw_dir / 'example.profraw').write_bytes(b'raw fixture')
            tool = build_dir / 'fake-profdata.py'
            tool.write_text(
                'import pathlib, sys\\n'
                'if sys.argv[1] == "merge":\\n'
                '    output = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("-output="))\\n'
                '    pathlib.Path(output).write_bytes(b"indexed fixture")\\n'
                'elif sys.argv[1] == "show":\\n'
                '    sys.exit(0 if pathlib.Path(sys.argv[2]).read_bytes() == b"indexed fixture" else 1)\\n'
                'else: sys.exit(1)\\n',
                encoding='utf-8',
            )
            env = os.environ.copy()
            env['LLVM_PROFDATA'] = (
                shlex.quote(sys.executable) + ' ' + shlex.quote(str(tool)))
            proc = subprocess.run(
                [sys.executable, str(PGO_HELPER), '--build-dir', temp],
                text=True, capture_output=True, check=False, env=env,
            )
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertIn('merged 1 raw profiles', proc.stdout)
            self.assertEqual((build_dir / 'default.profdata').read_bytes(),
                             b'indexed fixture')


if __name__ == '__main__':
    unittest.main()
