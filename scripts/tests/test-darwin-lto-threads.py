#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DARWIN_MESON = ROOT / 'configs' / 'meson' / 'darwin.txt'


class DarwinLtoThreadPolicyTests(unittest.TestCase):
    def test_darwin_does_not_force_single_threaded_lto(self):
        text = DARWIN_MESON.read_text(encoding='utf-8')
        self.assertIn('[built-in options]', text)
        self.assertIn('b_lto_threads = 0', text)
        self.assertNotIn('b_lto_threads = 1', text)

    def test_darwin_uses_cached_thinlto_for_incremental_links(self):
        text = DARWIN_MESON.read_text(encoding='utf-8')
        self.assertIn("b_lto_mode = 'thin'", text)
        self.assertIn('b_thinlto_cache = true', text)


if __name__ == '__main__':
    unittest.main()
