/*
 * OPTi 486WB register smoke tests
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "libqtest.h"
#define IDX 0x22
#define DAT 0x24
static uint8_t rd(QTestState *s, uint8_t idx)
{
    qtest_outb(s, IDX, idx);
    return qtest_inb(s, DAT);
}
static void wr(QTestState *s, uint8_t idx, uint8_t val)
{
    qtest_outb(s, IDX, idx);
    qtest_outb(s, DAT, val);
}
static void test_regs(void)
{
    QTestState *s = qtest_init("-machine opti-486wb -display none");
    g_assert_cmphex(rd(s, 0x20), ==, 0x00);
    g_assert_cmphex(rd(s, 0x22), ==, 0x84);
    g_assert_cmphex(rd(s, 0x24), ==, 0x87);
    g_assert_cmphex(rd(s, 0x27), ==, 0x91);
    wr(s, 0x20, 0xff);
    g_assert_cmphex(rd(s, 0x20), ==, 0x1f);
    g_assert_cmphex(qtest_inb(s, DAT), ==, 0xff);
    qtest_outb(s, DAT, 0);
    g_assert_cmphex(rd(s, 0x20), ==, 0x1f);
    wr(s, 0x22, 0xff);
    g_assert_cmphex(rd(s, 0x22), ==, 0xfd);
    qtest_outb(s, IDX, 0x30);
    g_assert_cmphex(qtest_inb(s, DAT), ==, 0xff);
    qtest_quit(s);
}
int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    if (qtest_has_machine("opti-486wb")) {
        qtest_add_func("/opti-486wb/registers", test_regs);
    }
    return g_test_run();
}
