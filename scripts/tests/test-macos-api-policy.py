#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]
COCOA = ROOT / 'ui' / 'cocoa.m'


class MacOSApiPolicyTests(unittest.TestCase):
    def test_legacy_corevideo_is_only_built_for_pre_macos12_targets(self):
        text = COCOA.read_text(encoding='utf-8')

        legacy_guard = (
            '#if MAC_OS_X_VERSION_MIN_REQUIRED < MAC_OS_VERSION_12_0\n'
            '#pragma clang diagnostic push\n'
            '#pragma clang diagnostic ignored "-Wdeprecated-declarations"\n\n'
            'static bool cocoa_legacy_refresh_rate'
        )
        self.assertIn(legacy_guard, text)

        fallback_guard = (
            '#if MAC_OS_X_VERSION_MIN_REQUIRED < MAC_OS_VERSION_12_0\n'
            '    return cocoa_legacy_refresh_rate(display, rate);\n'
            '#else\n'
            '    return false;\n'
            '#endif'
        )
        self.assertIn(fallback_guard, text)

    def test_modern_refresh_rate_api_remains_primary(self):
        text = COCOA.read_text(encoding='utf-8')
        modern = text.index('minimumRefreshInterval')
        legacy = text.index('cocoa_legacy_refresh_rate')
        self.assertLess(modern, legacy)


if __name__ == '__main__':
    unittest.main()
