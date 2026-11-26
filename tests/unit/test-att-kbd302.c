/*
 * AT&T 302 raw keyboard protocol tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/input/att-kbd302.h"
#include "standard-headers/linux/input-event-codes.h"

static void test_make_break(void)
{
    AttKbd302Core s;
    uint8_t value = 0xff;

    att_kbd302_core_reset(&s);
    g_assert_false(att_kbd302_core_read(&s, &value));
    g_assert_cmphex(value, ==, 0xff);
    for (unsigned int code = 1; code <= ATT_KBD302_SCAN_MAX; code++) {
        g_assert_true(att_kbd302_core_key(&s, code, true));
        g_assert_true(att_kbd302_core_key(&s, code, true));
        g_assert_true(att_kbd302_core_key(&s, code, false));
        g_assert_true(att_kbd302_core_read(&s, &value));
        g_assert_cmphex(value, ==, code);
        g_assert_true(att_kbd302_core_read(&s, &value));
        g_assert_cmphex(value, ==, code | 0x80);
        g_assert_false(att_kbd302_core_read(&s, &value));
    }
    g_assert_false(att_kbd302_core_key(&s, 0, true));
    g_assert_false(att_kbd302_core_key(&s, ATT_KBD302_SCAN_MAX + 1, true));
    g_assert_false(att_kbd302_core_key(&s, UINT_MAX, true));
}

static void test_queue(void)
{
    AttKbd302Core s;
    uint8_t value;

    att_kbd302_core_reset(&s);
    for (unsigned int i = 0; i < ATT_KBD302_QUEUE_SIZE; i++) {
        g_assert_true(att_kbd302_core_key(&s, 0x1e, !(i & 1)));
    }
    g_assert_false(att_kbd302_core_key(&s, 0x1e, true));
    g_assert_false(s.pressed[0x1e]);
    g_assert_true(att_kbd302_core_read(&s, &value));
    g_assert_cmphex(value, ==, 0x1e);
    g_assert_true(att_kbd302_core_key(&s, 0x1e, true));
    for (unsigned int i = 1; i <= ATT_KBD302_QUEUE_SIZE; i++) {
        g_assert_true(att_kbd302_core_read(&s, &value));
        g_assert_cmphex(value, ==, (i & 1) ? 0x9e : 0x1e);
    }
    g_assert_false(att_kbd302_core_read(&s, &value));
    att_kbd302_core_reset(&s);
    g_assert_false(s.pressed[0x1e]);
    g_assert_true(att_kbd302_core_key(&s, 0x1e, true));
    att_kbd302_core_reset(&s);
    g_assert_false(att_kbd302_core_read(&s, &value));
}

static void test_mapping(void)
{
    static const struct {
        unsigned int key;
        uint8_t scan;
    } cases[] = {
        { KEY_A, 0x1e }, { KEY_F10, 0x44 }, { KEY_F11, 0x60 },
        { KEY_F12, 0x61 }, { KEY_F18, 0x67 },
        { KEY_LEFT, 0x58 }, { KEY_DOWN, 0x59 },
        { KEY_RIGHT, 0x5a }, { KEY_UP, 0x5b },
        { KEY_KP4, 0x4b }, { KEY_KP6, 0x4d },
        { KEY_KPENTER, 0x57 }, { KEY_KPSLASH, 0x5f },
        { KEY_HELP, 0x56 },
    };
    AttKbd302Core s;
    bool seen[ATT_KBD302_SCAN_MAX + 1] = { false };
    uint8_t value;

    att_kbd302_core_reset(&s);
    for (unsigned int i = 0; i < ARRAY_SIZE(cases); i++) {
        g_assert_cmphex(att_kbd302_linux_to_scan(cases[i].key),
                        ==, cases[i].scan);
        g_assert_true(att_kbd302_core_linux_key(&s, cases[i].key, true));
        g_assert_true(att_kbd302_core_linux_key(&s, cases[i].key, false));
        g_assert_true(att_kbd302_core_read(&s, &value));
        g_assert_cmphex(value, ==, cases[i].scan);
        g_assert_true(att_kbd302_core_read(&s, &value));
        g_assert_cmphex(value, ==, cases[i].scan | 0x80);
    }
    for (unsigned int key = 0; key <= KEY_MAX; key++) {
        uint8_t scan = att_kbd302_linux_to_scan(key);

        if (scan) {
            g_assert_cmpuint(scan, <=, ATT_KBD302_SCAN_MAX);
            g_assert_false(seen[scan]);
            seen[scan] = true;
        }
    }
    g_assert_false(att_kbd302_core_linux_key(&s, KEY_LEFTMETA, true));
    g_assert_false(att_kbd302_core_linux_key(&s, KEY_RIGHTCTRL, true));
    g_assert_false(att_kbd302_core_linux_key(&s, KEY_F19, true));
    g_assert_false(att_kbd302_core_linux_key(&s, UINT_MAX, true));
    g_assert_false(att_kbd302_core_read(&s, &value));
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/att-kbd302/make-break", test_make_break);
    g_test_add_func("/att-kbd302/queue", test_queue);
    g_test_add_func("/att-kbd302/mapping", test_mapping);
    return g_test_run();
}
