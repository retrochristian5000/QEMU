/*
 * Serial mouse identification and modem-control regression.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

#define COM1 0x3f8
#define MCR (COM1 + 4)
#define LSR (COM1 + 5)

typedef struct MouseTest {
    const char *backend;
    const char *legacy_id;
    const char *pnp_id;
} MouseTest;

static const MouseTest profiles[] = {
    { "msmouse", "M", "PNP0F01" },
    { "logitech-mouseman", "M3", "PNP0F08" },
};

static void check_identification(QTestState *s, const MouseTest *test)
{
    uint8_t bytes[64];
    unsigned len = 0;
    size_t prefix = strlen(test->legacy_id);

    while (qtest_inb(s, LSR) & 1) {
        g_assert_cmpuint(len, <, sizeof(bytes));
        bytes[len++] = qtest_inb(s, COM1);
    }

    g_assert_cmpuint(len, >=, prefix + 10);
    g_assert_cmpmem(bytes, prefix, test->legacy_id, prefix);
    g_assert_cmphex(bytes[prefix], ==, '(' - 0x20);
    for (unsigned i = 0; i < 7; i++) {
        g_assert_cmphex(bytes[prefix + 3 + i] + 0x20, ==,
                        test->pnp_id[i]);
    }
    g_assert_cmphex(bytes[len - 1], ==, ')' - 0x20);
}

static void test_mouse(gconstpointer opaque)
{
    const MouseTest *test = opaque;
    QTestState *s = qtest_initf("-M pc -nodefaults -serial %s", test->backend);

    qtest_outb(s, COM1 + 3, 0x80);
    qtest_outb(s, COM1, 96); /* 115200 / 96 = 1200 baud */
    qtest_outb(s, COM1 + 1, 0);
    qtest_outb(s, COM1 + 3, 2); /* 7N1 */
    qtest_outb(s, COM1 + 2, 7); /* Enable and clear FIFO */
    qtest_outb(s, MCR, 0);
    qtest_outb(s, MCR, 1); /* DTR alone is not a completed reset. */
    g_assert_cmphex(qtest_inb(s, LSR) & 1, ==, 0);
    qtest_outb(s, MCR, 3);
    check_identification(s, test);

    /* Repeat detection by toggling only RTS, leaving DTR asserted. */
    qtest_outb(s, MCR, 1);
    qtest_outb(s, MCR, 3);
    check_identification(s, test);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    for (unsigned i = 0; i < ARRAY_SIZE(profiles); i++) {
        g_autofree char *name = g_strdup_printf("/serial-mouse/%s",
                                                profiles[i].backend);
        qtest_add_data_func(name, &profiles[i], test_mouse);
    }
    return g_test_run();
}
