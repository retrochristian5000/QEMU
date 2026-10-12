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
            '    (void)display;\n'
            '    return false;\n'
            '#endif'
        )
        self.assertIn(fallback_guard, text)

    def test_modern_refresh_rate_api_remains_primary(self):
        text = COCOA.read_text(encoding='utf-8')
        modern = text.index('minimumRefreshInterval')
        legacy = text.index('cocoa_legacy_refresh_rate')
        self.assertLess(modern, legacy)

    def test_graphical_consoles_have_independent_cocoa_windows(self):
        text = COCOA.read_text(encoding='utf-8')
        start = text.index('- (void)createAdditionalConsoleWindows\n{')
        end = text.index('\n}\n', start)
        create = text[start:end]

        # A second host monitor alone must not duplicate the guest's output:
        # windows are associated with distinct *graphical* QEMU heads.
        self.assertIn('qemu_console_lookup_by_index(index)', create)
        self.assertIn('qemu_console_is_graphic(guest)', create)
        self.assertIn('guest == console.con', create)
        self.assertIn('qemu_console_register_listener(guest, &extra->dcl,',
                      create)
        self.assertIn('qkbd_state_init(extra->dcl.con)', create)
        self.assertIn('qemu_add_mouse_mode_change_notifier(', create)
        self.assertIn('[NSScreen screens]', create)
        self.assertIn('[target visibleFrame]', create)
        self.assertIn('g_ptr_array_add(extraConsoles, extra)', create)

    def test_input_focus_and_cleanup_are_per_window(self):
        text = COCOA.read_text(encoding='utf-8')
        self.assertIn('NSWindow *window = [event window] ?: [NSApp keyWindow]',
                      text)
        self.assertIn('[controller viewForWindow:window]', text)
        self.assertIn('[[self viewForWindow:[notification object]] updateUIInfo]',
                      text)
        self.assertIn('[[self viewForWindow:[notification object]] grabMouse]',
                      text)
        self.assertIn('[[extra->view window] makeKeyAndOrderFront:self]', text)
        self.assertIn('qemu_console_unregister_listener(&extra->dcl)', text)
        self.assertIn('g_clear_pointer(&extra->kbd, qkbd_state_free)', text)
        self.assertIn('&extra->mouse_mode_change_notifier', text)
        self.assertIn('if (cocoa->is_primary &&', text)
        self.assertIn('if (!allow_events || !console->dcl.con || !console->con)',
                      text)


if __name__ == '__main__':
    unittest.main()
