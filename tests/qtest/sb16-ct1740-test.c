/*
 * Creative CT1740 fixed-jumper PCM profile tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"

static uint8_t mixer_read(QTestState *s, unsigned int base, uint8_t reg)
{
    qtest_outb(s, base + 4, reg);
    return qtest_inb(s, base + 5);
}

static void mixer_write(QTestState *s, unsigned int base, uint8_t reg,
                        uint8_t value)
{
    qtest_outb(s, base + 4, reg);
    qtest_outb(s, base + 5, value);
}

static void test_ct1740_probe(gconstpointer data)
{
    bool alternate = GPOINTER_TO_UINT(data);
    unsigned int base = alternate ? 0x240 : 0x220;
    unsigned int irq = alternate ? 10 : 5;
    unsigned int dma = alternate ? 3 : 1;
    unsigned int hdma = alternate ? 7 : 5;
    unsigned int irq_mask = alternate ? 8 : 2;
    unsigned int dma_mask = (1U << dma) | (1U << hdma);
    QTestState *s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                               "-device sb16,audiodev=snd,iobase=0x%x,"
                               "irq=%u,dma=%u,dma16=%u", base, irq, dma, hdma);

    qtest_outb(s, base + 6, 1);
    qtest_outb(s, base + 6, 0);
    g_assert_cmphex(qtest_inb(s, base + 0xe) & 0x80, ==, 0x80);
    g_assert_cmphex(qtest_inb(s, base + 0xa), ==, 0xaa);
    qtest_outb(s, base + 0xc, 0xe1);
    g_assert_cmphex(qtest_inb(s, base + 0xa), ==, 4);
    g_assert_cmphex(qtest_inb(s, base + 0xa), ==, 5);
    g_assert_cmphex(mixer_read(s, base, 0x80), ==, irq_mask);
    g_assert_cmphex(mixer_read(s, base, 0x81), ==, dma_mask);

    mixer_write(s, base, 0x80, 1);
    mixer_write(s, base, 0x81, 0x41);
    mixer_write(s, base, 0, 0);
    g_assert_cmphex(mixer_read(s, base, 0x80), ==, irq_mask);
    g_assert_cmphex(mixer_read(s, base, 0x81), ==, dma_mask);

    qtest_outb(s, base + 0xc, 0xf2);
    qtest_outb(s, base + 0xc, 0xf3);
    g_assert_cmphex(mixer_read(s, base, 0x82) & 3, ==, 3);
    qtest_inb(s, base + 0xe);
    g_assert_cmphex(mixer_read(s, base, 0x82) & 3, ==, 2);
    qtest_inb(s, base + 0xf);
    g_assert_cmphex(mixer_read(s, base, 0x82) & 3, ==, 0);
    qtest_quit(s);
}

static void test_ct1740_invalid(gconstpointer data)
{
    const char *properties = data;

    if (g_test_subprocess()) {
        QTestState *s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                                   "-device sb16,audiodev=snd,%s", properties);
        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*sb16: CT1740*");
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    if (qtest_has_machine("pc") && qtest_has_device("sb16")) {
        qtest_add_data_func("/ct1740/default", GUINT_TO_POINTER(0),
                            test_ct1740_probe);
        qtest_add_data_func("/ct1740/alternate", GUINT_TO_POINTER(1),
                            test_ct1740_probe);
        qtest_add_data_func("/ct1740/invalid-base", "iobase=0x230",
                            test_ct1740_invalid);
        qtest_add_data_func("/ct1740/invalid-irq", "irq=3",
                            test_ct1740_invalid);
        qtest_add_data_func("/ct1740/invalid-dma", "dma=2",
                            test_ct1740_invalid);
        qtest_add_data_func("/ct1740/invalid-hdma", "dma16=1",
                            test_ct1740_invalid);
        qtest_add_data_func("/ct1740/invalid-version", "version=0x040d",
                            test_ct1740_invalid);
    }
    return g_test_run();
}
