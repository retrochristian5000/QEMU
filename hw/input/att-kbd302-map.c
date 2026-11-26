/*
 * Provisional AT&T 302 host-key mapping.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Reference: Olivetti M24/M21 Theory of Operation (Nov 1984),
 * chapter 6, scan-code table and figure 6-2 (keyboard 2 layout).
 * https://kbd-project.org/docs/scancodes/m24kbd.png
 *
 * The related deluxe layout is a reference, not a verified US 302
 * key matrix. Leave ambiguous punctuation, modern modifiers and
 * combined navigation functions unmapped rather than inventing codes
 * or aliasing two simultaneously held host keys to one physical key.
 */

#include "qemu/osdep.h"
#include "hw/input/att-kbd302.h"
#include "standard-headers/linux/input-event-codes.h"

static const uint8_t att_kbd302_keymap[KEY_MAX + 1] = {
    [KEY_ESC] = 0x01,
    [KEY_1] = 0x02,
    [KEY_2] = 0x03,
    [KEY_3] = 0x04,
    [KEY_4] = 0x05,
    [KEY_5] = 0x06,
    [KEY_6] = 0x07,
    [KEY_7] = 0x08,
    [KEY_8] = 0x09,
    [KEY_9] = 0x0a,
    [KEY_0] = 0x0b,
    [KEY_MINUS] = 0x0c,
    [KEY_BACKSPACE] = 0x0e,
    [KEY_TAB] = 0x0f,
    [KEY_Q] = 0x10,
    [KEY_W] = 0x11,
    [KEY_E] = 0x12,
    [KEY_R] = 0x13,
    [KEY_T] = 0x14,
    [KEY_Y] = 0x15,
    [KEY_U] = 0x16,
    [KEY_I] = 0x17,
    [KEY_O] = 0x18,
    [KEY_P] = 0x19,
    [KEY_ENTER] = 0x1c,
    [KEY_LEFTCTRL] = 0x1d,
    [KEY_A] = 0x1e,
    [KEY_S] = 0x1f,
    [KEY_D] = 0x20,
    [KEY_F] = 0x21,
    [KEY_G] = 0x22,
    [KEY_H] = 0x23,
    [KEY_J] = 0x24,
    [KEY_K] = 0x25,
    [KEY_L] = 0x26,
    [KEY_SEMICOLON] = 0x27,
    [KEY_LEFTSHIFT] = 0x2a,
    [KEY_102ND] = 0x2b,
    [KEY_Z] = 0x2c,
    [KEY_X] = 0x2d,
    [KEY_C] = 0x2e,
    [KEY_V] = 0x2f,
    [KEY_B] = 0x30,
    [KEY_N] = 0x31,
    [KEY_M] = 0x32,
    [KEY_COMMA] = 0x33,
    [KEY_DOT] = 0x34,
    [KEY_SLASH] = 0x35,
    [KEY_RIGHTSHIFT] = 0x36,
    [KEY_KPASTERISK] = 0x37,
    [KEY_LEFTALT] = 0x38,
    [KEY_SPACE] = 0x39,
    [KEY_CAPSLOCK] = 0x3a,
    [KEY_F1] = 0x3b,
    [KEY_F2] = 0x3c,
    [KEY_F3] = 0x3d,
    [KEY_F4] = 0x3e,
    [KEY_F5] = 0x3f,
    [KEY_F6] = 0x40,
    [KEY_F7] = 0x41,
    [KEY_F8] = 0x42,
    [KEY_F9] = 0x43,
    [KEY_F10] = 0x44,
    [KEY_SCROLLLOCK] = 0x46,
    [KEY_KP7] = 0x47,
    [KEY_KP8] = 0x48,
    [KEY_KP9] = 0x49,
    [KEY_KPMINUS] = 0x4a,
    [KEY_KP4] = 0x4b,
    [KEY_KP5] = 0x4c,
    [KEY_KP6] = 0x4d,
    [KEY_KPPLUS] = 0x4e,
    [KEY_KP1] = 0x4f,
    [KEY_KP2] = 0x50,
    [KEY_KP3] = 0x51,
    [KEY_KP0] = 0x52,
    [KEY_KPDOT] = 0x53,
    [KEY_SYSRQ] = 0x55,
    [KEY_HELP] = 0x56,
    [KEY_KPENTER] = 0x57,
    [KEY_LEFT] = 0x58,
    [KEY_DOWN] = 0x59,
    [KEY_RIGHT] = 0x5a,
    [KEY_UP] = 0x5b,
    [KEY_KPSLASH] = 0x5f,
    [KEY_F11] = 0x60,
    [KEY_F12] = 0x61,
    [KEY_F13] = 0x62,
    [KEY_F14] = 0x63,
    [KEY_F15] = 0x64,
    [KEY_F16] = 0x65,
    [KEY_F17] = 0x66,
    [KEY_F18] = 0x67,
};

uint8_t att_kbd302_linux_to_scan(unsigned int key)
{
    if (key >= ARRAY_SIZE(att_kbd302_keymap)) {
        return 0;
    }
    return att_kbd302_keymap[key];
}

bool att_kbd302_core_linux_key(AttKbd302Core *s, unsigned int key, bool down)
{
    uint8_t scan = att_kbd302_linux_to_scan(key);

    return scan && att_kbd302_core_key(s, scan, down);
}
