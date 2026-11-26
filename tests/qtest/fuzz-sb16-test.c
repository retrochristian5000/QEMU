/*
 * QTest fuzzer-generated testcase for sb16 audio device
 *
 * Copyright (c) 2021 Philippe Mathieu-Daudé
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"

/*
 * This used to trigger the assert in audio_calloc
 * https://bugs.launchpad.net/qemu/+bug/1910603
 */
static void test_fuzz_sb16_0x1c(void)
{
    QTestState *s = qtest_init("-M q35 "
                               "-device sb16,audiodev=snd0 "
                               "-audiodev none,id=snd0");
    qtest_outw(s, 0x22c, 0x41);
    qtest_outb(s, 0x22c, 0x00);
    qtest_outw(s, 0x22c, 0x1004);
    qtest_outw(s, 0x22c, 0x001c);
    qtest_quit(s);
}

static void test_fuzz_sb16_0x91(void)
{
    QTestState *s = qtest_init("-M pc "
                               "-device sb16,audiodev=none "
                               "-audiodev id=none,driver=none");
    qtest_outw(s, 0x22c, 0xf141);
    qtest_outb(s, 0x22c, 0x00);
    qtest_outb(s, 0x22c, 0x24);
    qtest_outb(s, 0x22c, 0x91);
    qtest_quit(s);
}

/*
 * This used to trigger the assert in audio_calloc
 * through command 0xd4
 */
static void test_fuzz_sb16_0xd4(void)
{
    QTestState *s = qtest_init("-M pc "
                               "-device sb16,audiodev=none "
                               "-audiodev id=none,driver=none");
    qtest_outb(s, 0x22c, 0x41);
    qtest_outb(s, 0x22c, 0x00);
    qtest_outb(s, 0x22c, 0x14);
    qtest_outb(s, 0x22c, 0xd4);
    qtest_quit(s);
}

static void csp_write(QTestState *s, uint8_t reg, uint8_t value)
{
    qtest_outb(s, 0x22c, 0x0e);
    qtest_outb(s, 0x22c, reg);
    qtest_outb(s, 0x22c, value);
}

static uint8_t csp_read(QTestState *s, uint8_t reg)
{
    qtest_outb(s, 0x22c, 0x0f);
    qtest_outb(s, 0x22c, reg);
    g_assert_cmphex(qtest_inb(s, 0x22e) & 0x80, ==, 0x80);
    return qtest_inb(s, 0x22a);
}

static void test_sb16_csp_registers(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                               "-device sb16,audiodev=none "
                               "-audiodev id=none,driver=none");

    qtest_outb(s, 0x226, 1);
    qtest_outb(s, 0x226, 0);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xaa);

    csp_write(s, 0x20, 0x55);
    csp_write(s, 0x21, 0xa5);
    g_assert_cmphex(csp_read(s, 0x20), ==, 0x55);
    g_assert_cmphex(csp_read(s, 0x21), ==, 0xa5);
    csp_write(s, 0x20, 0);
    g_assert_cmphex(csp_read(s, 0x20), ==, 0);
    g_assert_cmphex(csp_read(s, 0x21), ==, 0xa5);

    /* Preserve the existing four-byte register 0x83 sequence. */
    qtest_outb(s, 0x22c, 0x04);
    qtest_outb(s, 0x22c, 0);
    for (unsigned i = 0; i < 5; i++) {
        csp_write(s, 0x83, 0x30 + i);
    }
    g_assert_cmphex(csp_read(s, 0x83), ==, 0x34);
    for (unsigned i = 1; i < 4; i++) {
        g_assert_cmphex(csp_read(s, 0x83), ==, 0x30 + i);
    }
    g_assert_cmphex(csp_read(s, 0x83), ==, 0x34);

    /* The next ordinary DSP command must still be decoded correctly. */
    qtest_outb(s, 0x22c, 0xe0);
    qtest_outb(s, 0x22c, 0x55);
    g_assert_cmphex(qtest_inb(s, 0x22a), ==, 0xaa);

    qtest_quit(s);
}

static void test_awe32_reserved(void)
{
    if (g_test_subprocess()) {
        QTestState *s = qtest_init("-M pc -nodefaults -device awe32");

        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr("*awe32: EMU8000 synthesis and sound memory "
                              "are not implemented*");
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);

    if (qtest_has_machine("q35")) {
        qtest_add_func("fuzz/test_fuzz_sb16/1c", test_fuzz_sb16_0x1c);
    }
    if (qtest_has_machine("pc")) {
        qtest_add_func("fuzz/test_fuzz_sb16/91", test_fuzz_sb16_0x91);
        qtest_add_func("fuzz/test_fuzz_sb16/d4", test_fuzz_sb16_0xd4);
        qtest_add_func("/sb16/csp/registers", test_sb16_csp_registers);
        if (qtest_has_device("awe32")) {
            qtest_add_func("/awe32/reserved", test_awe32_reserved);
        }
    }

    return g_test_run();
}
