#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline regression coverage for WHP's managed sccacher bootstrap."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'ensure-sccache.py'

spec = importlib.util.spec_from_file_location('whp_ensure_sccache', BOOTSTRAP)
bootstrap = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(bootstrap)


class ManagedSccacheTests(unittest.TestCase):
    def test_cargo_seed_selection_and_rejection(self):
        seed = ROOT / 'seeds' / 'cargo.sh'
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            cargo = base / 'cargo'
            cargo.write_text(
                '#!/bin/sh\n'
                'case "$1" in\n'
                '  --version) echo "cargo 1.91.0 (fixture)" ;;\n'
                '  --whp-cargo-adapter-probe) exit 2 ;;\n'
                '  *) echo "cargo fixture: $1" ;;\n'
                'esac\n', encoding='utf-8')
            cargo.chmod(0o755)
            env = {**os.environ, 'WHP_CARGO_SEED': str(cargo)}
            chosen = subprocess.run(
                ['/bin/sh', str(seed), '--print-seed'],
                env=env, capture_output=True, text=True, check=True)
            self.assertEqual(chosen.stdout.strip(), str(cargo.resolve()))
            forwarded = subprocess.run(
                ['/bin/sh', str(seed), '--version'],
                env=env, capture_output=True, text=True, check=True)
            self.assertIn('cargo 1.91.0', forwarded.stdout)
            env['WHP_CARGO_SEED'] = str(base / 'missing')
            rejected = subprocess.run(
                ['/bin/sh', str(seed), '--print-seed'],
                env=env, capture_output=True, text=True)
            self.assertNotEqual(rejected.returncode, 0)
            self.assertIn('WHP_CARGO_SEED', rejected.stderr)
            env['WHP_CARGO_SEED'] = str(seed)
            recursive = subprocess.run(
                ['/bin/sh', str(seed), '--print-seed'],
                env=env, capture_output=True, text=True, timeout=10)
            self.assertNotEqual(recursive.returncode, 0)

    def test_sccacher_uses_cargo_seed(self):
        source = BOOTSTRAP.read_text(encoding='utf-8')
        self.assertIn("str(ROOT / 'seeds/cargo.sh')", source)
        self.assertIn("str(ROOT / 'seeds/rustc.sh')", source)
        self.assertNotIn("shutil.which('cargo')", source)
        self.assertNotIn("shutil.which('rustc')", source)

    def test_rustc_seed_selection_and_rejection(self):
        seed = ROOT / 'seeds' / 'rustc.sh'
        with tempfile.TemporaryDirectory() as directory:
            base = pathlib.Path(directory)
            rustc = base / 'rustc'
            rustc.write_text(
                '#!/bin/sh\n'
                'case "$1" in\n'
                '  --version) echo "rustc 1.91.0 (fixture)" ;;\n'
                '  --whp-rustc-adapter-probe) exit 2 ;;\n'
                '  *) echo "rustc fixture: $1" ;;\n'
                'esac\n', encoding='utf-8')
            rustc.chmod(0o755)
            env = {**os.environ, 'WHP_RUSTC_SEED': str(rustc)}
            chosen = subprocess.run(
                ['/bin/sh', str(seed), '--print-seed'],
                env=env, capture_output=True, text=True, check=True)
            self.assertEqual(chosen.stdout.strip(), str(rustc.resolve()))
            forwarded = subprocess.run(
                ['/bin/sh', str(seed), '--version'],
                env=env, capture_output=True, text=True, check=True)
            self.assertIn('rustc 1.91.0', forwarded.stdout)
            for invalid in (base / 'missing', seed):
                env['WHP_RUSTC_SEED'] = str(invalid)
                rejected = subprocess.run(
                    ['/bin/sh', str(seed), '--print-seed'],
                    env=env, capture_output=True, text=True, timeout=10)
                self.assertNotEqual(rejected.returncode, 0)

    def test_cargo_build_is_memory_conservative(self):
        env = bootstrap.cargo_environment({
            'RUSTC_WRAPPER': '/old/sccache',
            'CARGO_BUILD_RUSTC_WRAPPER': '/other/cache',
            'CARGO_ENCODED_RUSTFLAGS': '-Copt-level=3',
            'SCCACHE_DIR': '/cache',
            'CC_FOR_BUILD': '/native/clang',
        }, pathlib.Path('/tmp/sccache-target'))
        self.assertNotIn('RUSTC_WRAPPER', env)
        self.assertNotIn('CARGO_BUILD_RUSTC_WRAPPER', env)
        self.assertNotIn('CARGO_ENCODED_RUSTFLAGS', env)
        self.assertEqual(env['CARGO_PROFILE_RELEASE_LTO'], 'false')
        self.assertEqual(env['CARGO_PROFILE_RELEASE_CODEGEN_UNITS'], '8')
        self.assertEqual(env['CARGO_TARGET_DIR'], '/tmp/sccache-target')
        self.assertEqual(env['SCCACHE_DIR'], '/cache')
        # An outer Rust compiler is target state, not a host seed.
        self.assertNotIn('RUSTC', bootstrap.cargo_environment(
            {'CC_FOR_BUILD': '/native/clang', 'RUSTC': '/guest/rustc'},
            pathlib.Path('/tmp/sccache-target')))
        chosen = bootstrap.cargo_environment(
            {'CC_FOR_BUILD': '/native/clang', 'RUSTC': '/guest/rustc'},
            pathlib.Path('/tmp/sccache-target'), rustc='/native/rustc')
        self.assertEqual(chosen['RUSTC'], '/native/rustc')

    def test_cargo_build_uses_native_compiler_environment(self):
        qemu_flags = {
            'CPPFLAGS': '-I/guest/include',
            'CFLAGS': '-include guest-config.h',
            'CXXFLAGS': '-include guest-config.h',
            'LDFLAGS': '-L/guest/lib',
            'CPATH': '/guest/include',
            'C_INCLUDE_PATH': '/guest/c-headers',
            'HOST_CFLAGS': '-I/guest/host-headers',
            'HOST_CC': '/guest/host-cc',
            'HOST_CPPFLAGS': '-DWRONG_HEADER=1',
            'HOSTCFLAGS': '-I/guest/legacy-headers',
            'CC_aarch64_apple_darwin': '/guest/cross-cc',
            'CFLAGS_aarch64_apple_darwin': '-I/guest/target-headers',
            'TARGET_CC': '/guest/target-cc',
            'CXX': '/guest/cross-cxx',
            'CPP': '/guest/cross-cpp',
            'HOST_CXX': '/guest/host-cxx',
            'HOST_CPP': '/guest/host-cpp',
            'HOST_CXXFLAGS': '-std=c++11 -I/guest/cxx',
            'CXXFLAGS_aarch64_apple_darwin': '-I/guest/cxx-target',
            'CPPFLAGS_aarch64_apple_darwin': '-DWRONG_SDK=1',
            'CXX_aarch64_apple_darwin': '/guest/cross-cxx',
            'CPP_aarch64_apple_darwin': '/guest/cross-cpp',
            'HOST_CXXFLAGS_aarch64_apple_darwin': '-I/guest/host',
            'HOST_CPPFLAGS_aarch64_apple_darwin': '-DHOST_WRONG=1',
            'TARGET_CXX': '/guest/target-cxx',
            'TARGET_CPP': '/guest/target-cpp',
            'TARGET_CXXFLAGS': '-I/guest/cxx-target',
            'TARGET_CPPFLAGS': '-DWRONG_CPP=1',
            # Cargo has its own cross-target controls, separate from CFLAGS
            # and QEMU's CC/CXX. None may redirect the native sccache build.
            'CARGO_BUILD_TARGET': 'aarch64-unknown-linux-gnu',
            'CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_LINKER': '/guest/ld',
            'CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUSTFLAGS': '-Ctarget-cpu=native',
            'CARGO_TARGET_AARCH64_UNKNOWN_LINUX_GNU_RUNNER': '/guest/runner',
            'CARGO_BUILD_RUSTC': '/guest/rustc',
            'CARGO_BUILD_RUSTDOC': '/guest/rustdoc',
            'CARGO_BUILD_RUSTFLAGS': '-Clinker=/guest/ld',
            'RUSTDOCFLAGS': '-L/guest/rustlib',
            'CARGO_ENCODED_RUSTDOCFLAGS': '-L\\x1f/guest/rustlib',
        }
        native = {
            'CC_FOR_BUILD': '/native/clang',
            'CXX_FOR_BUILD': '/native/clang++',
            'CPP_FOR_BUILD': '/native/cpp',
            'SDKROOT': '/native/MacOSX.sdk',
            'DEVELOPER_DIR': '/native/Developer',
            'MACOSX_DEPLOYMENT_TARGET': '15.0',
            'CARGO_HOME': '/cargo',
        }
        env = bootstrap.cargo_environment(
            {
                **qemu_flags, **native,
                'CC': 'sccache /guest/cc',
                'HOST_CC': '/old/clang',
            },
            pathlib.Path('/tmp/sccache-target'),
        )
        self.assertEqual((qemu_flags.keys() - {'HOST_CC', 'HOST_CXX', 'CXX'}) & env.keys(), set())
        self.assertEqual(env['CC'], native['CC_FOR_BUILD'])
        self.assertEqual(env['HOST_CC'], native['CC_FOR_BUILD'])
        self.assertEqual(env['CXX'], native['CXX_FOR_BUILD'])
        self.assertEqual(env['HOST_CXX'], native['CXX_FOR_BUILD'])
        self.assertNotIn('CPP', env)
        self.assertNotIn('CXXFLAGS', env)
        self.assertNotIn('CPPFLAGS', env)
        self.assertEqual({key: env[key] for key in native}, native)
        self.assertNotIn('CARGO_BUILD_TARGET', env)
        self.assertNotIn('CARGO_BUILD_RUSTC', env)
        self.assertNotIn('CARGO_BUILD_RUSTDOC', env)
        self.assertNotIn('CARGO_BUILD_RUSTFLAGS', env)
        self.assertNotIn('RUSTDOCFLAGS', env)
        self.assertNotIn('CARGO_ENCODED_RUSTDOCFLAGS', env)
        self.assertFalse(any(key.startswith('CARGO_TARGET_') and key != 'CARGO_TARGET_DIR' for key in env))

    def test_cargo_target_dir_is_native_and_replaces_inherited_override(self):
        env = bootstrap.cargo_environment({
            'CC_FOR_BUILD': '/native/clang',
            'CXX_FOR_BUILD': '/native/clang++',
            'CARGO_BUILD_TARGET': 'x86_64-pc-windows-gnu',
            'CARGO_TARGET_DIR': '/guest/cache',
            'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER': '/guest/ld',
            'CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS': '-Clinker=/guest/ld',
            'CARGO_BUILD_RUSTC': '/guest/rustc',
            'CARGO_BUILD_RUSTFLAGS': '-Ctarget-feature=+unknown',
            'RUSTC': '/guest/rustc',
        }, pathlib.Path('/native/build/work'), rustc='/native/rustc')
        self.assertEqual(env['CC'], '/native/clang')
        self.assertEqual(env['HOST_CC'], '/native/clang')
        self.assertEqual(env['CXX'], '/native/clang++')
        self.assertEqual(env['HOST_CXX'], '/native/clang++')
        self.assertEqual(env['RUSTC'], '/native/rustc')
        self.assertEqual(env['CARGO_TARGET_DIR'], '/native/build/work')
        self.assertNotIn('CARGO_BUILD_TARGET', env)
        self.assertNotIn('CARGO_BUILD_RUSTC', env)
        self.assertNotIn('CARGO_BUILD_RUSTFLAGS', env)
        self.assertNotIn('CARGO_TARGET_X86_64_PC_WINDOWS_GNU_LINKER', env)
        self.assertNotIn('CARGO_TARGET_X86_64_PC_WINDOWS_GNU_RUSTFLAGS', env)

    def test_cargo_requires_explicit_native_compiler(self):
        with self.assertRaisesRegex(RuntimeError, 'CC_FOR_BUILD'):
            bootstrap.cargo_environment(
                {'HOST_CC': '/guest/cc', 'HOST_CFLAGS': '-I/guest/include'},
                pathlib.Path('/tmp/sccache-target'))

    def test_job_override_is_strict(self):
        self.assertEqual(bootstrap.build_jobs({}), 2)
        self.assertEqual(bootstrap.build_jobs({'WHP_SCCACHE_BUILD_JOBS': '1'}), 1)
        for bad in ('', '0', '-1', '1 2', '2x'):
            with self.subTest(value=bad), self.assertRaises(ValueError):
                bootstrap.build_jobs({'WHP_SCCACHE_BUILD_JOBS': bad})

    def test_source_is_pinned_submodule(self):
        modules = (ROOT / '.gitmodules').read_text(encoding='utf-8')
        self.assertIn('[submodule "toolchains/sccacher"]', modules)
        self.assertIn('https://github.com/retrochristian5000/sccacher.git', modules)
        self.assertEqual(bootstrap.SUBMODULE, pathlib.Path('toolchains/sccacher'))
        source = BOOTSTRAP.read_text(encoding='utf-8')
        self.assertIn('reconcile_submodule(ROOT, SUBMODULE, git=git)', source)
        self.assertIn("'--locked'", source)
        self.assertIn("'--no-default-features'", source)

    def test_pinned_source_uses_reconciled_checkout(self):
        with tempfile.TemporaryDirectory() as directory:
            root = pathlib.Path(directory)
            source = root / bootstrap.SUBMODULE
            source.mkdir(parents=True)
            (source / 'Cargo.toml').write_text('[package]\nname = "dummy"\n', encoding='utf-8')
            (source / 'Cargo.lock').write_text('version = 3\n', encoding='utf-8')
            revision = 'a' * 40
            with mock.patch.object(bootstrap, 'ROOT', root), \
                 mock.patch.dict(os.environ, {'GIT': '/native/bin/git'}), \
                 mock.patch.object(bootstrap, 'reconcile_submodule',
                                   return_value=revision) as reconcile, \
                 mock.patch.object(bootstrap, 'call', return_value='') as call:
                self.assertEqual(bootstrap.pinned_source(), (source, revision))
                reconcile.assert_called_once_with(
                    root, bootstrap.SUBMODULE, git='/native/bin/git')
                call.assert_called_once_with(
                    ['/native/bin/git', '-C', str(source), 'status', '--porcelain',
                     '--untracked-files=no'], capture=True)

    def test_cached_binary_skips_cargo(self):
        with tempfile.TemporaryDirectory() as directory:
            build = pathlib.Path(directory)
            host = f'{bootstrap.platform.system().lower()}-{bootstrap.platform.machine().lower()}'
            prefix = build / 'toolchains' / 'sccache' / host
            binary = prefix / 'bin' / 'sccache'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\necho sccache-0.18.0\n', encoding='utf-8')
            binary.chmod(0o755)
            identity = {
                'schema': bootstrap.SCHEMA, 'gitlink': 'a' * 40,
                'rustc_path': '/native/rustc', 'rustc': 'rustc 1.91.0',
                'cargo': 'cargo 1.91.0',
                'features': 'local-only', 'profile': 'lto=false,codegen-units=8,debug=0',
            }
            (prefix / '.whp-sccacher.json').write_text(json.dumps(identity))
            with mock.patch.object(bootstrap, 'pinned_source', return_value=(build, 'a' * 40)), \
                 mock.patch.object(bootstrap, 'host_tools', return_value=('cargo', '/native/rustc', 'rustc 1.91.0', 'cargo 1.91.0')), \
                 mock.patch.object(bootstrap, 'call', return_value='sccache-0.18.0') as run:
                self.assertEqual(bootstrap.ensure(build), binary)
                run.assert_called_once_with([str(binary), '--version'], capture=True)

    def test_qemu_selects_fork_after_host_dependencies_before_native_llvm(self):
        text = (ROOT / 'build.sh').read_text(encoding='utf-8')
        host_tools = (ROOT / 'scripts/whp-build/host-tools.sh').read_text(
            encoding='utf-8')
        self.assertIn('whp_prepare_git_dependent_cache()', text)
        self.assertLess(text.index('scripts/whp-build/update-submodules.py'),
                        text.index('scripts/ensure-sccache.py'))
        self.assertLess(text.index('scripts/ensure-sccache.py'),
                        text.index('scripts/bootstrap-native-clang.sh'))
        # The function is declared before the host-tool module is sourced,
        # but called only once Git has been promoted and before Ninja/Bash.
        self.assertLess(text.index('whp_prepare_git_dependent_cache()'),
                        text.index('. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"'))
        self.assertLess(host_tools.index('WHP_GIT_SEED"'),
                        host_tools.index('whp_prepare_git_dependent_cache || exit 1'))
        self.assertLess(host_tools.index('whp_prepare_git_dependent_cache || exit 1'),
                        host_tools.index('BOOTSTRAP_NINJA=$('))
        self.assertLess(host_tools.index('whp_prepare_git_dependent_cache || exit 1'),
                        host_tools.index('BOOTSTRAP_BASH=$('))
        self.assertIn('WHP_COMPILER_CACHE_CMD=$(', text)
        self.assertIn('COMPILER_CACHE=sccache', text)
        self.assertLess(text.index('seeds/cxx.sh" --print-cxx'),
                        text.index('scripts/ensure-sccache.py'))
        self.assertIn('export CXX_FOR_BUILD', text)


if __name__ == '__main__':
    unittest.main()
