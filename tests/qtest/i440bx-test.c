/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "libqtest.h"
#include "hw/pci/pci_regs.h"

static uint8_t bx_readb(QTestState *s, unsigned reg)
{
    qtest_outl(s, 0xcf8, 0x80000000 | (reg & ~3));
    return qtest_inb(s, 0xcfc + (reg & 3));
}

static void bx_writeb(QTestState *s, unsigned reg, uint8_t val)
{
    qtest_outl(s, 0xcf8, 0x80000000 | (reg & ~3));
    qtest_outb(s, 0xcfc + (reg & 3), val);
}

static void test_i440bx_config(void)
{
    /*
     * qtest does not execute firmware; stock BIOS is sufficient for
     * configuration-space checks while the CPU remains stopped.
     */
    QTestState *s = qtest_init("-machine pc-i440bx -m 256M "
                               "-bios bios-256k.bin -nic none");
    unsigned i;

    qtest_outl(s, 0xcf8, 0x80000000);
    g_assert_cmphex(qtest_inl(s, 0xcfc), ==, 0x71928086);
    qtest_outl(s, 0xcf8, 0x80000004);
    g_assert_cmphex(qtest_inw(s, 0xcfc), ==, 0x0006);
    g_assert_cmphex(qtest_inw(s, 0xcfe), ==, 0x0200);
    g_assert_cmphex(bx_readb(s, 0x57), ==, 0);
    g_assert_cmphex(bx_readb(s, 0x58), ==, 3);
    g_assert_cmphex(bx_readb(s, 0x7a), ==, 2);
    g_assert_cmphex(bx_readb(s, 0x60), ==, 16);
    for (i = 0x61; i <= 0x67; i++) {
        g_assert_cmphex(bx_readb(s, i), ==, 32);
    }

    bx_writeb(s, 0x7a, 0xff);
    g_assert_cmphex(bx_readb(s, 0x7a), ==, 2);
    bx_writeb(s, 0x67, 0xff);
    g_assert_cmphex(bx_readb(s, 0x67), ==, 32);
    bx_writeb(s, 0x59, 0xff);
    g_assert_cmphex(bx_readb(s, 0x59), ==, 0x30);
    bx_writeb(s, 0x5a, 0xff);
    g_assert_cmphex(bx_readb(s, 0x5a), ==, 0x33);

    bx_writeb(s, 0x72, 0x48);
    g_assert_cmphex(bx_readb(s, 0x72), ==, 0x4a);
    bx_writeb(s, 0x72, 0x58);
    g_assert_cmphex(bx_readb(s, 0x72), ==, 0x1a);
    bx_writeb(s, 0x72, 0x48);
    g_assert_cmphex(bx_readb(s, 0x72), ==, 0x1a);
    bx_writeb(s, 0x72, 0);
    g_assert_cmphex(bx_readb(s, 0x72), ==, 0x1a);

    qtest_system_reset(s);
    g_assert_cmphex(bx_readb(s, 0x72), ==, 2);
    g_assert_cmphex(bx_readb(s, 0x59), ==, 0);
    g_assert_cmphex(bx_readb(s, 0x5a), ==, 0);
    g_assert_cmphex(bx_readb(s, 0x67), ==, 32);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("i440bx/config", test_i440bx_config);
    return g_test_run();
}
