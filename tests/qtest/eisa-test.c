/*
 * QTest coverage for the EISA configuration mechanism
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "libqtest.h"

#define EISA_VENDOR_ID 0x0c80
#define EISA_CONTROL   0x0c84
#define EISA_SLOT_SIZE 0x1000

static void test_dell_system_board(const void *data)
{
    const char *machine = data;
    QTestState *s;
    uint8_t product_low;

    s = qtest_initf("-machine %s -display none", machine);

    /* DEL encodes to 0x10, 0xac; 0001/0002 distinguishes the siblings. */
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 0), ==, 0x10);
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 1), ==, 0xac);
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 2), ==, 0x00);

    product_low = !strcmp(machine, "dell-system-425e") ? 0x01 : 0x02;
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 3), ==, product_low);

    /* Slot 0 starts enabled and the standardized ENABLE bit is writable. */
    g_assert_cmphex(qtest_inb(s, EISA_CONTROL), ==, 0x01);
    qtest_outb(s, EISA_CONTROL, 0x00);
    g_assert_cmphex(qtest_inb(s, EISA_CONTROL), ==, 0x00);
    qtest_outb(s, EISA_CONTROL, 0x01);
    g_assert_cmphex(qtest_inb(s, EISA_CONTROL), ==, 0x01);

    /* No EISA adapter has been installed in slot 1. */
    g_assert_cmphex(qtest_inb(s, EISA_SLOT_SIZE + EISA_VENDOR_ID), ==, 0xff);

    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    if (qtest_has_machine("dell-system-425e")) {
        qtest_add_data_func("/eisa/dell-system-425e", "dell-system-425e",
                            test_dell_system_board);
    }
    if (qtest_has_machine("dell-system-433e")) {
        qtest_add_data_func("/eisa/dell-system-433e", "dell-system-433e",
                            test_dell_system_board);
    }

    return g_test_run();
}
