/*
 * Creative CT1300 / Game Blaster ISA I/O separation.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

static void test_gameblaster_io(void)
{
    QTestState *qts = qtest_init("-M pc -nodefaults "
                                 "-audiodev none,id=snd0 "
                                 "-device gameblaster,audiodev=snd0");

    g_assert_cmphex(qtest_inb(qts, 0x224), ==, 0x7f);
    g_assert_cmphex(qtest_inb(qts, 0x22a), ==, 0);
    qtest_outb(qts, 0x226, 0xa5);
    g_assert_cmphex(qtest_inb(qts, 0x22a), ==, 0xa5);
    g_assert_cmphex(qtest_inb(qts, 0x22b), ==, 0xa5);
    qtest_outb(qts, 0x227, 0x5a);
    g_assert_cmphex(qtest_inb(qts, 0x22a), ==, 0x5a);

    /* Each SAA1099 uses its own address/data pair and is write-only. */
    qtest_outb(qts, 0x221, 0x00);
    qtest_outb(qts, 0x220, 0xf0);
    qtest_outb(qts, 0x223, 0x00);
    qtest_outb(qts, 0x222, 0x0f);
    g_assert_cmphex(qtest_inb(qts, 0x220), ==, 0xff);
    g_assert_cmphex(qtest_inb(qts, 0x222), ==, 0xff);

    /* No SB DSP version, mixer, DMA or IRQ interface exists on the CT1300. */
    g_assert_cmphex(qtest_inb(qts, 0x22e), ==, 0xff);
    qtest_quit(qts);
}

static void test_gameblaster_alt_base(void)
{
    QTestState *qts = qtest_init("-M pc -nodefaults "
                                 "-audiodev none,id=snd0 "
                                 "-device gameblaster,audiodev=snd0,iobase=0x240");

    qtest_outb(qts, 0x246, 0x36);
    g_assert_cmphex(qtest_inb(qts, 0x24a), ==, 0x36);
    g_assert_cmphex(qtest_inb(qts, 0x244), ==, 0x7f);
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    if (qtest_has_machine("pc")) {
        qtest_add_func("/gameblaster/io", test_gameblaster_io);
        qtest_add_func("/gameblaster/alternate-base", test_gameblaster_alt_base);
    }
    return g_test_run();
}
