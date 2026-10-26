#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import os
import pathlib
import platform
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DARWIN_MESON = ROOT / 'configs' / 'meson' / 'darwin.txt'
PREPARE_BUILD = ROOT / 'scripts' / 'whp-build' / 'prepare-build.bash'
LTO_PROBE = ROOT / 'scripts' / 'verify-macos-lto.bash'
PORTABLE_BUILD = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'


class DarwinLtoThreadPolicyTests(unittest.TestCase):
    @unittest.skipUnless(sys.platform in ('linux', 'darwin'), 'requires Unix archive tools')
    def test_macos_lto_probe_replaces_corrupt_prior_archive(self):
        compiler = shutil.which('clang' if sys.platform == 'darwin' else 'gcc')
        archiver = shutil.which('ar')
        ranlib = shutil.which('ranlib')
        if not all((compiler, archiver, ranlib)):
            self.skipTest('compiler, ar, and ranlib are required')

        with tempfile.TemporaryDirectory(prefix='whp-lto-archive-') as temp:
            root = pathlib.Path(temp)
            (root / 'sdk').mkdir()
            probe = root / 'probe'
            probe.mkdir()
            archive = probe / 'liblto-probe.a'
            archive.write_bytes(b'broken archive')

            # Only macOS has xcrun; LIPO reports the host slice of the
            # executable so the rest of the actual probe can run on Linux.
            fake_bin = root / 'bin'
            fake_bin.mkdir()
            xcrun = fake_bin / 'xcrun'
            xcrun.write_text('#!/bin/sh\nexit 0\n', encoding='utf-8')
            xcrun.chmod(0o755)
            lipo = fake_bin / 'lipo'
            arch = 'arm64' if platform.machine() in ('arm64', 'aarch64') else 'x86_64'
            lipo.write_text(f'#!/bin/sh\nprintf "%s\\n" "{arch}"\n', encoding='utf-8')
            lipo.chmod(0o755)

            env = dict(os.environ)
            env.update(PATH=f'{fake_bin}{os.pathsep}{env.get("PATH", "")}',
                       CC=compiler, AR=archiver, RANLIB=ranlib,
                       SDKROOT=str(root / 'sdk'), LIPO=str(lipo),
                       MACOS_LTO_PROBE_DIR=str(probe),
                       MACOS_LTO_MANIFEST=str(root / 'manifest'),
                       QEMU_HOST_LTO_MODE='full', JOBS='',
                       CFLAGS='', CPPFLAGS='', LDFLAGS='')
            result = subprocess.run(['bash', str(LTO_PROBE)], cwd=root, env=env,
                                    capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertTrue(archive.read_bytes().startswith(b'!<arch>\n'))
            self.assertIn('ARCHIVE=' + str(archive),
                          (root / 'manifest').read_text(encoding='utf-8'))

    def test_darwin_does_not_force_single_threaded_lto(self):
        text = DARWIN_MESON.read_text(encoding='utf-8')
        self.assertIn('[built-in options]', text)
        self.assertIn('b_lto_threads = 0', text)
        self.assertNotIn('b_lto_threads = 1', text)

    def test_darwin_configure_uses_compile_power_budget_for_lto(self):
        text = PREPARE_BUILD.read_text(encoding='utf-8')
        self.assertIn('configure_args+=("-Db_lto_threads=$JOBS")', text)
        self.assertNotIn('configure_args+=(-Db_lto_threads=0)', text)

    def test_macos_preflight_matches_meson_thinlto(self):
        text = LTO_PROBE.read_text(encoding='utf-8')
        self.assertIn('auto|thin) lto_mode=thin; lto_flag=-flto=thin', text)
        self.assertIn('full) lto_mode=full; lto_flag=-flto', text)
        self.assertIn('"$lto_flag" -c "$source_a"', text)
        self.assertIn('"$lto_flag" -c "$source_main"', text)
        self.assertIn("printf 'LTO_MODE=%s\\n' \"$lto_mode\"", text)
        self.assertIn('WHP_MACOS_LTO_SCHEMA=3', text)
        self.assertIn('"${AR_CMD[@]}" rcs "$archive_candidate" "$object_a"', text)
        self.assertIn('"${RANLIB_CMD[@]}" "$archive_candidate"', text)
        self.assertIn('"$object_main" "$archive" -o "$output"', text)
        self.assertIn('set_archive_command AR /usr/bin/ar', text)
        self.assertIn('set_archive_command RANLIB /usr/bin/ranlib', text)
        self.assertIn('THINLTO_JOBS_ARG=("-flto-jobs=$JOBS")', text)
        self.assertIn('"${THINLTO_JOBS_ARG[@]}" "$object_main" "$archive"', text)
        self.assertIn("printf 'LTO_JOBS=%s\\n'", text)

    def test_bash_and_portable_paths_cap_link_workers(self):
        bash = PREPARE_BUILD.read_text(encoding='utf-8')
        portable = PORTABLE_BUILD.read_text(encoding='utf-8')
        self.assertIn('configure_args+=("-Db_lto_threads=$JOBS")', bash)
        self.assertIn('f"-Db_lto_threads={resolved_jobs(', portable)
        self.assertIn("optional_switch(configure_args, lto, 'lto')", portable)
        self.assertIn('whp_add_optional_configure_switch "$QEMU_HOST_LTO" lto', bash)
        self.assertIn('configure_args+=(-Db_lto_mode=thin)', bash)
        self.assertIn('configure_args+=(-Db_lto_mode=default -Db_thinlto_cache=false)', bash)
        self.assertIn("configure_args.append('-Db_lto_mode=thin')", portable)
        self.assertIn("'-Db_lto_mode=default', '-Db_thinlto_cache=false'", portable)

    def test_darwin_uses_cached_thinlto_for_incremental_links(self):
        text = DARWIN_MESON.read_text(encoding='utf-8')
        self.assertIn("b_lto_mode = 'thin'", text)
        self.assertIn('b_thinlto_cache = true', text)


if __name__ == '__main__':
    unittest.main()
