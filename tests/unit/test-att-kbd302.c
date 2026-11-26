/*
 * AT&T 302 raw keyboard protocol tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/input/att-kbd302.h"

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

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/att-kbd302/make-break", test_make_break);
    g_test_add_func("/att-kbd302/queue", test_queue);
    return g_test_run();
}
