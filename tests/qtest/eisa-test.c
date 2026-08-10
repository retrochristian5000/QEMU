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

typedef struct DellEISATestData {
    const char *machine;
    uint8_t product_low;
} DellEISATestData;

static void test_dell_system_board(const void *opaque)
{
    const DellEISATestData *data = opaque;
    QTestState *s;

    s = qtest_initf("-machine %s -display none", data->machine);

    /* DEL encodes to 0x10, 0xac; the product bytes select the system board. */
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 0), ==, 0x10);
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 1), ==, 0xac);
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 2), ==, 0x00);
    g_assert_cmphex(qtest_inb(s, EISA_VENDOR_ID + 3), ==, data->product_low);

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
    static const DellEISATestData dell_systems[] = {
        { "dell-system-425e",  0x01 },
        { "dell-system-433e",  0x02 },
        { "dell-system-433de", 0x05 },
    };
    int i;

    g_test_init(&argc, &argv, NULL);

    for (i = 0; i < ARRAY_SIZE(dell_systems); i++) {
        const DellEISATestData *data = &dell_systems[i];

        if (qtest_has_machine(data->machine)) {
            char *path = g_strdup_printf("/eisa/%s", data->machine);

            qtest_add_data_func(path, data, test_dell_system_board);
            g_free(path);
        }
    }

    return g_test_run();
}
