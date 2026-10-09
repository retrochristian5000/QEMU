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
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
PORTABLE_BUILD_ENTRY = ROOT / 'scripts' / 'whp-build' / 'portable-build-entry.py'
BUILDER = ROOT / 'builder.bash'
PGO_HELPER = ROOT / 'scripts' / 'whp-build' / 'pgo-profile.py'
BUILD_ENTRY = ROOT / 'build.sh'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_portable_module():
    spec = importlib.util.spec_from_file_location('whp_portable_core', PORTABLE_BUILD_TOOL)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


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
                'import pathlib, sys\n'
                'if sys.argv[1] == "merge":\n'
                '    output = next(a.split("=", 1)[1] for a in sys.argv if a.startswith("-output="))\n'
                '    pathlib.Path(output).write_bytes(b"indexed fixture")\n'
                'elif sys.argv[1] == "show":\n'
                '    sys.exit(0 if pathlib.Path(sys.argv[2]).read_bytes() == b"indexed fixture" else 1)\n'
                'else: sys.exit(1)\n',
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


    def test_pgo_status_requires_real_profile_data(self):
        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td)
            def status():
                return subprocess.run(
                    [sys.executable, str(PGO_HELPER),
                     '--mode', 'status', '--build-dir', td],
                    capture_output=True, text=True, check=False,
                )
            self.assertEqual(status().stdout.strip(), 'generate')
            raw_dir = path / 'pgo-raw'
            raw_dir.mkdir()
            (raw_dir / 'empty.profraw').touch()
            self.assertEqual(status().stdout.strip(), 'generate')
            (raw_dir / 'nonempty.profraw').write_bytes(b'raw')
            self.assertEqual(status().stdout.strip(), 'use')
            (raw_dir / 'nonempty.profraw').unlink()
            (path / 'default.profdata').write_bytes(b'indexed')
            self.assertEqual(status().stdout.strip(), 'use')

    def test_public_use_launches_generate_without_tests_or_install(self):
        build_entry = BUILD_ENTRY.read_text(encoding='utf-8')
        self.assertIn('QEMU_HOST_PGO=generate WHP_PGO_GENERATION_CHILD=1', build_entry)
        self.assertIn('WHP_SOURCE_UPDATE_DONE=1 RUN_TESTS=0 INSTALL_AFTER_BUILD=0',
                      build_entry)
        self.assertIn('"$SOURCE_DIR/build.sh" "$@"', build_entry)
        self.assertIn('--mode status --build-dir "$BUILD_DIR"', build_entry)
        self.assertIn('QEMU_PGO_TRAIN_SCRIPT', build_entry)
        self.assertIn('LLVM_PROFILE_FILE="$BUILD_DIR/pgo-raw/%m-%p.profraw"',
                      build_entry)

    def test_portable_generate_stage_trains_before_pgo_use(self):
        mod = load_portable_module()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            script = build_dir / 'train.sh'
            script.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            script.chmod(0o755)
            calls = []

            def fake_run(cmd, **kwargs):
                calls.append((list(cmd), kwargs))
                if '--mode' in cmd and 'status' in cmd:
                    return subprocess.CompletedProcess(cmd, 0, stdout='use\n')
                return subprocess.CompletedProcess(cmd, 0)

            with mock.patch.dict(os.environ, {'QEMU_PGO_TRAIN_SCRIPT': str(script)}), \\
                 mock.patch.object(mod.subprocess, 'run', side_effect=fake_run), \\
                 mock.patch.object(mod, 'append_module_build_target'), \\
                 mock.patch.object(mod, 'write_portable_config'):
                mod.portable_pgo_generate(
                    build_dir, build_dir / 'install',
                    ['--disable-system', '-Db_pgo=use'], ['all'],
                    ['ninja'], '2', {'QEMU_HOST_MODULES': 'auto'},
                )
            self.assertIn('-Db_pgo=generate', calls[0][0])
            self.assertNotIn('-Db_pgo=use', calls[0][0])
            self.assertEqual(calls[1][0][0], 'ninja')
            self.assertEqual(calls[2][0][0], str(script))
            self.assertIn('LLVM_PROFILE_FILE', calls[2][1]['env'])
            self.assertEqual(calls[2][1]['env']['WHP_PGO_BUILD_DIR'],
                             str(build_dir))
            self.assertIn('--mode', calls[3][0])

    def test_portable_use_generates_then_requests_training_when_missing(self):
        mod = load_portable_module()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            with mock.patch.dict(os.environ, {'QEMU_PGO_TRAIN_SCRIPT': ''}), \\
                 mock.patch.object(mod.subprocess, 'run') as runner, \\
                 mock.patch.object(mod, 'append_module_build_target'), \\
                 mock.patch.object(mod, 'write_portable_config'):
                with self.assertRaisesRegex(RuntimeError,
                                            'instrumented QEMU generate build is ready'):
                    mod.portable_pgo_generate(
                        build_dir, build_dir / 'install',
                        ['--disable-system', '-Db_pgo=use'],
                        ['qemu-system-ppc'], ['ninja'], '2',
                        {'QEMU_HOST_MODULES': 'auto'},
                    )
                self.assertTrue((build_dir / 'pgo-raw').is_dir())
                self.assertEqual(runner.call_count, 2)


if __name__ == '__main__':
    unittest.main()
