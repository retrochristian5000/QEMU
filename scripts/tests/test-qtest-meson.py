#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard QTest Meson list continuations and Game Blaster registration."""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
QTEST_MESON = ROOT / "tests/qtest/meson.build"


class QTestMesonTests(unittest.TestCase):
    def test_i386_qtest_entries_preserve_line_continuation(self):
        text = QTEST_MESON.read_text(encoding="utf-8")
        start = text.index("qtests_i386 = ")
        end = text.index("\nif dbus_display", start)
        block = text[start:end]
        for line_number, line in enumerate(block.splitlines(), 1):
            with self.subTest(line=line_number):
                self.assertFalse(
                    re.search(r"\+\s*$", line),
                    f"qtests_i386 expression has an unterminated + "
                    f"(relative line {line_number}): {line}",
                )

    def test_gameblaster_test_is_conditional_and_has_a_source(self):
        text = QTEST_MESON.read_text(encoding="utf-8")
        self.assertIn(
            "(config_all_devices.has_key('CONFIG_GAMEBLASTER') "
            "? ['gameblaster-test'] : []) + " + chr(92),
            text,
        )
        self.assertTrue((ROOT / "tests/qtest/gameblaster-test.c").is_file())
        self.assertIn(
            "config GAMEBLASTER",
            (ROOT / "hw/audio/Kconfig").read_text(encoding="utf-8"),
        )
        self.assertIn(
            "CONFIG_GAMEBLASTER",
            (ROOT / "hw/audio/meson.build").read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
