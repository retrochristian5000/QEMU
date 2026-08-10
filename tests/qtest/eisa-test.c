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

#define ET4000_HERC_COMPAT    0x03bf
#define ET4000_SEGMENT_SELECT 0x03cd
#define ET4000_MODE_COLOR     0x03d8
#define VGA_SEQ_INDEX         0x03c4
#define VGA_SEQ_DATA          0x03c5

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

static void test_dell_433de_et4000ax(void)
{
    QTestState *s;

    s = qtest_initf("-machine dell-system-433de -display none");

    /* Tseng's segment register is inaccessible until the KEY sequence. */
    g_assert_cmphex(qtest_inb(s, ET4000_SEGMENT_SELECT), ==, 0xff);
    qtest_outb(s, ET4000_SEGMENT_SELECT, 0x21);
    g_assert_cmphex(qtest_inb(s, ET4000_SEGMENT_SELECT), ==, 0xff);

    /* ET4000 data book KEY: 3BF=03h followed by 3D8=A0h in color mode. */
    qtest_outb(s, ET4000_HERC_COMPAT, 0x03);
    qtest_outb(s, ET4000_MODE_COLOR, 0xa0);
    g_assert_cmphex(qtest_inb(s, ET4000_SEGMENT_SELECT), ==, 0x00);

    /* Low nibble is the write bank; high nibble is the independent read bank. */
    qtest_outb(s, ET4000_SEGMENT_SELECT, 0x21);
    g_assert_cmphex(qtest_inb(s, ET4000_SEGMENT_SELECT), ==, 0x21);

    /* A synchronous timing-sequencer reset requires KEY to be set again. */
    qtest_outb(s, VGA_SEQ_INDEX, 0x00);
    qtest_outb(s, VGA_SEQ_DATA, 0x01);
    g_assert_cmphex(qtest_inb(s, ET4000_SEGMENT_SELECT), ==, 0xff);

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

    if (qtest_has_machine("dell-system-433de") &&
        qtest_has_device("isa-et4000ax")) {
        qtest_add_func("/eisa/dell-system-433de/et4000ax",
                       test_dell_433de_et4000ax);
    }

    return g_test_run();
}
