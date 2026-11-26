/*
 * PIIX integrated ISA DMA controller register tests.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

static void test_piix_dma_masks(gconstpointer opaque)
{
    const char *machine = opaque;
    QTestState *s = qtest_initf("-M %s -nodefaults", machine);
    g_autofree char *tree = qtest_hmp(s, "info qtree");
    g_auto(GStrv) types = g_strsplit(tree, "dev: piix-82c37,", -1);

    g_assert_cmpuint(g_strv_length(types), ==, 3);
    g_assert_null(strstr(tree, "dev: i8257,"));

    qtest_outb(s, 0x0d, 0);
    qtest_outb(s, 0xda, 0);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 0x0f);
    g_assert_cmphex(qtest_inb(s, 0xde), ==, 0x0f);
    g_assert_cmphex(qtest_inb(s, 0x09), ==, 0);
    g_assert_cmphex(qtest_inb(s, 0xd2), ==, 0);

    /* Mask banks are independent; reserved bits do not latch. */
    qtest_outb(s, 0x0f, 0xa5);
    qtest_outb(s, 0xde, 0xfa);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 5);
    g_assert_cmphex(qtest_inb(s, 0xde), ==, 10);
    qtest_outb(s, 0x0a, 0x06);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 5);
    qtest_outb(s, 0x0a, 0x02);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 1);
    qtest_outb(s, 0xd4, 0x04);
    g_assert_cmphex(qtest_inb(s, 0xde), ==, 11);
    qtest_outb(s, 0xdc, 0);
    g_assert_cmphex(qtest_inb(s, 0xde), ==, 0);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 1);
    qtest_outb(s, 0x0e, 0);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 0);

    /* A disabled controller retains pending request status. */
    qtest_outb(s, 0x08, 4);
    qtest_outb(s, 0x0b, 0x82);
    qtest_outb(s, 0x09, 6);
    g_assert_cmphex(qtest_inb(s, 0x08) & 0x40, ==, 0x40);
    qtest_outb(s, 0x09, 2);
    g_assert_cmphex(qtest_inb(s, 0x08) & 0x40, ==, 0);
    qtest_system_reset(s);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 0x0f);
    g_assert_cmphex(qtest_inb(s, 0xde), ==, 0x0f);
    qtest_quit(s);
}

static void test_piix_dma_compat(void)
{
    QTestState *s = qtest_init("-M pc,chipset-controllers=off -nodefaults");
    g_autofree char *tree = qtest_hmp(s, "info qtree");
    g_auto(GStrv) types = g_strsplit(tree, "dev: i8257,", -1);

    g_assert_cmpuint(g_strv_length(types), ==, 3);
    g_assert_null(strstr(tree, "dev: piix-82c37,"));
    qtest_outb(s, 0x0f, 0x05);
    g_assert_cmphex(qtest_inb(s, 0x09), ==, 0x05);
    g_assert_cmphex(qtest_inb(s, 0x0f), ==, 0);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_data_func("/piix/dma/piix3", "pc,chipset-controllers=on",
                        test_piix_dma_masks);
    if (qtest_has_machine("pc-i440bx")) {
        qtest_add_data_func("/piix/dma/piix4",
                            "pc-i440bx,chipset-controllers=on",
                            test_piix_dma_masks);
    }
    qtest_add_func("/piix/dma/compat", test_piix_dma_compat);
    return g_test_run();
}
