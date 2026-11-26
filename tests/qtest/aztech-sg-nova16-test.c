/*
 * Aztech Nova 16 DSP identification, independent of Creative SB16.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

static void test_nova16_probe(gconstpointer data)
{
    unsigned int base = GPOINTER_TO_UINT(data);
    QTestState *qts = qtest_initf("-M pc -nodefaults "
                                "-device aztech-sg-nova16,iobase=0x%x", base);

    g_assert_cmphex(qtest_inb(qts, base + 0x0e), ==, 0);
    qtest_outb(qts, base + 6, 1);
    qtest_outb(qts, base + 6, 0);
    g_assert_cmphex(qtest_inb(qts, base + 0x0e), ==, 0x80);
    g_assert_cmphex(qtest_inb(qts, base + 0x0a), ==, 0xaa);
    g_assert_cmphex(qtest_inb(qts, base + 0x0e), ==, 0);
    qtest_outb(qts, base + 0x0c, 0xe1);
    g_assert_cmphex(qtest_inb(qts, base + 0x0a), ==, 2);
    g_assert_cmphex(qtest_inb(qts, base + 0x0e), ==, 0x80);
    g_assert_cmphex(qtest_inb(qts, base + 0x0a), ==, 1);
    g_assert_cmphex(qtest_inb(qts, base + 0x0e), ==, 0);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    if (qtest_has_machine("pc")) {
        qtest_add_data_func("/nova16/default-base", GUINT_TO_POINTER(0x220),
                            test_nova16_probe);
        qtest_add_data_func("/nova16/alternate-base", GUINT_TO_POINTER(0x240),
                            test_nova16_probe);
    }
    return g_test_run();
}
