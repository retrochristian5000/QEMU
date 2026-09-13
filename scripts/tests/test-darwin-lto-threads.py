#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
DARWIN_MESON = ROOT / 'configs' / 'meson' / 'darwin.txt'


class DarwinLtoThreadPolicyTests(unittest.TestCase):
    def test_darwin_caps_lto_threads_to_one(self):
        text = DARWIN_MESON.read_text(encoding='utf-8')
        self.assertIn('[built-in options]', text)
        self.assertIn('b_lto_threads = 1', text)


if __name__ == '__main__':
    unittest.main()
