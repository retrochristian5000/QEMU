#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_DIR = ROOT / 'scripts' / 'whp-config'
CONFIG_TOOL = CONFIG_DIR / 'config.py'
MENU_TOOL = CONFIG_DIR / 'menuconfig.py'
sys.path.insert(0, str(CONFIG_DIR))


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config_scroll', CONFIG_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def load_menu_module():
    spec = importlib.util.spec_from_file_location('whp_menuconfig_scroll', MENU_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class FakeScreen:
    def __init__(self, keys, height=10, width=120):
        self.keys = list(keys)
        self.height = height
        self.width = width
        self.frames = []
        self.current = []

    def keypad(self, enabled):
        del enabled

    def erase(self):
        if self.current:
            self.frames.append(self.current)
        self.current = []

    def getmaxyx(self):
        return self.height, self.width

    def addnstr(self, y, x, text, limit, attr=0):
        self.current.append((y, x, str(text)[:limit], attr))

    def refresh(self):
        pass

    def getch(self):
        if not self.keys:
            raise AssertionError('menu requested more input than the test supplied')
        return self.keys.pop(0)


class MenuconfigScrollTests(unittest.TestCase):
    def test_selection_is_kept_inside_viewport(self):
        menu = load_menu_module()
        self.assertEqual(menu._scroll_top(20, 0, 0, 5), 0)
        self.assertEqual(menu._scroll_top(20, 5, 0, 5), 1)
        self.assertEqual(menu._scroll_top(20, 12, 8, 5), 8)
        self.assertEqual(menu._scroll_top(20, 3, 8, 5), 3)
        self.assertEqual(menu._scroll_top(20, 19, 3, 5), 15)

    def test_viewport_clamps_to_bounds(self):
        menu = load_menu_module()
        self.assertEqual(menu._scroll_top(3, 2, 100, 10), 0)
        self.assertEqual(menu._scroll_top(20, 19, 100, 5), 15)
        self.assertEqual(menu._scroll_top(20, 0, -5, 5), 0)
        self.assertEqual(menu._scroll_top(20, 10, 7, 0), 0)

    def test_save_message_persists_across_navigation_without_restoring_values(self):
        config = load_config_module()
        menu = load_menu_module()
        if menu.curses is None:
            self.skipTest('curses unavailable')

        state = config.ConfigState(config.default_values(), {})
        first_key = config.OPTIONS[0].key
        original = state.values[first_key]
        screen = FakeScreen([ord('s'), menu.curses.KEY_DOWN, ord('q')])

        with tempfile.TemporaryDirectory() as td:
            path = pathlib.Path(td) / '.whpconfig'
            with mock.patch.object(menu.curses, 'curs_set', return_value=None):
                menu._run(screen, path, state)
            if screen.current:
                screen.frames.append(screen.current)

            saved_text = f'Saved {path}'
            footer_y = screen.height - 2
            saved_frames = [
                frame for frame in screen.frames
                if any(y == footer_y and text == saved_text for y, _, text, _ in frame)
            ]
            self.assertGreaterEqual(len(saved_frames), 2)
            self.assertEqual(state.values[first_key], original)


if __name__ == '__main__':
    unittest.main()
