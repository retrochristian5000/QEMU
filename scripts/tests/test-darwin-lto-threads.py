#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DARWIN_MESON = ROOT / 'configs' / 'meson' / 'darwin.txt'
PREPARE_BUILD = ROOT / 'scripts' / 'whp-build' / 'prepare-build.bash'
LTO_PROBE = ROOT / 'scripts' / 'verify-macos-lto.bash'
PORTABLE_BUILD = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'


class DarwinLtoThreadPolicyTests(unittest.TestCase):
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
        self.assertIn('"${AR_CMD[@]}" rcs "$archive" "$object_a"', text)
        self.assertIn('"${RANLIB_CMD[@]}" "$archive"', text)
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
