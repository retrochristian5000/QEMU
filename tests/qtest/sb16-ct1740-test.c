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

static uint8_t ct1740_csp_read(QTestState *s, uint8_t reg)
{
    qtest_outb(s, 0x22c, 0x0f);
    qtest_outb(s, 0x22c, reg);
    g_assert_cmphex(qtest_inb(s, 0x22e) & 0x80, ==, 0x80);
    return qtest_inb(s, 0x22a);
}

static void test_ct1740_no_csp(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults -audiodev none,id=snd "
                               "-device sb16,audiodev=snd");
    uint8_t before;

    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xaa);

    /* Probe the optional coprocessor without confusing its state with PCM. */
    qtest_outb(s, 0x22c, 0x05);
    qtest_outb(s, 0x22c, 0);
    qtest_outb(s, 0x22c, 0);
    qtest_outb(s, 0x22c, 0x04);
    qtest_outb(s, 0x22c, 0xfc);
    before = ct1740_csp_read(s, 0x83);
    g_assert_cmphex(before, ==, 0xff);
    qtest_outb(s, 0x22c, 0x0e);
    qtest_outb(s, 0x22c, 0x83);
    qtest_outb(s, 0x22c, before ^ 0xff);
    g_assert_cmphex(ct1740_csp_read(s, 0x83), ==, before);
    qtest_outb(s, 0x22c, 0x08);
    qtest_outb(s, 0x22c, 0x03);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xff);

    /* Probe arguments must not be reinterpreted as ordinary DSP commands. */
    qtest_outb(s, 0x22c, 0x0e);
    qtest_outb(s, 0x22c, 0xe1);
    qtest_outb(s, 0x22c, 0xe0);
    g_assert_cmphex(qtest_inb(s, 0x22e) & 0x80, ==, 0);
    qtest_outb(s, 0x22c, 0xe1);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 4);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 5);
    qtest_quit(s);
}

static void test_sb16_no_emu8000(gconstpointer data)
{
    const char *model = data;
    QTestState *s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                               "-device %s,audiodev=snd", model);

    /* Default EMU8000 data and index windows are not SB16 DSP aliases. */
    for (unsigned int port = 0x620; port <= 0xe20; port += 0x400) {
        for (unsigned int offset = 0; offset < 4; offset += 2) {
            g_assert_cmphex(qtest_inw(s, port + offset), ==, 0xffff);
            qtest_outw(s, port + offset, 0x55aa);
            g_assert_cmphex(qtest_inw(s, port + offset), ==, 0xffff);
        }
    }

    /* The writes to absent synthesizer ports must not disturb the DSP. */
    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xaa);
    qtest_outb(s, 0x22c, 0xe1);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 4);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 5);
    qtest_quit(s);
}

typedef struct SB16BoardProbe {
    const char *type;
    const char *options;
    uint8_t minor;
} SB16BoardProbe;

static const SB16BoardProbe board_probes[] = {
    { "sb16-ct1730", "", 4 },
    { "sb16-ct1730", ",version=0x0405", 5 },
    { "sb16-ct1750", "", 5 },
    { "sb16-ct1750", ",version=0x040b", 11 },
    { "sb16-ct1770", "", 5 },
    { "sb16-ct1770", ",version=0x040c", 12 },
    { "sb16-ct1790", "", 11 },
};

static void test_sb16_legacy_board(gconstpointer data)
{
    const SB16BoardProbe *probe = data;
    QTestState *s = qtest_initf("-M pc -nodefaults -audiodev none,id=snd "
                               "-device %s,audiodev=snd%s",
                               probe->type, probe->options);

    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xaa);
    qtest_outb(s, 0x22c, 0xe1);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 4);
    g_assert_cmpuint(qtest_inb(s, 0x22a), ==, probe->minor);
    g_assert_cmphex(mixer_read(s, 0x220, 0x80), ==, 2);
    g_assert_cmphex(mixer_read(s, 0x220, 0x81), ==, 0x22);
    g_assert_cmphex(ct1740_csp_read(s, 0x83), ==, 0xff);
    for (unsigned int port = 0x620; port <= 0xe20; port += 0x400) {
        g_assert_cmphex(qtest_inw(s, port), ==, 0xffff);
        g_assert_cmphex(qtest_inw(s, port + 2), ==, 0xffff);
    }
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
        qtest_add_func("/ct1740/no-csp", test_ct1740_no_csp);
        qtest_add_data_func("/ct1740/no-emu8000", "sb16",
                            test_sb16_no_emu8000);
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
        qtest_add_data_func("/ct1740/invalid-midi-base", "mpu-iobase=0x310",
                            test_ct1740_invalid);
    }
    if (qtest_has_machine("pc") && qtest_has_device("sb16-generic")) {
        qtest_add_data_func("/sb16-generic/no-emu8000", "sb16-generic",
                            test_sb16_no_emu8000);
    }
    if (qtest_has_machine("pc")) {
        for (size_t i = 0; i < G_N_ELEMENTS(board_probes); i++) {
            if (qtest_has_device(board_probes[i].type)) {
                g_autofree char *path = g_strdup_printf("/sb16/%s/dsp-%u",
                                                       board_probes[i].type,
                                                       board_probes[i].minor);
                qtest_add_data_func(path, &board_probes[i],
                                    test_sb16_legacy_board);
            }
        }
    }
    return g_test_run();
}
