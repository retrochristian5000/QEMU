/*
 * NE2000 ISA resource routing and reset regression tests.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "libqtest.h"

#define NE2K_BASE       0x300
#define NE2K_IRQ        9
#define NE2K_CR         (NE2K_BASE + 0x00)
#define NE2K_ISR        (NE2K_BASE + 0x07)
#define NE2K_RBCR0      (NE2K_BASE + 0x0a)
#define NE2K_RBCR1      (NE2K_BASE + 0x0b)
#define NE2K_IMR        (NE2K_BASE + 0x0f)
#define NE2K_RESET      (NE2K_BASE + 0x1f)

#define CR_START        0x02
#define CR_REMOTE_READ  0x08
#define CR_STOP_NODMA   0x21
#define ISR_RDC         0x40
#define ISR_RST         0x80

static void test_reset_irq(void)
{
    QTestState *s = qtest_init("-machine pc -nodefaults "
                              "-device ne2k_isa,iobase=0x300,irq=9");

    qtest_irq_intercept_in(s, "ioapic");
    qtest_outb(s, NE2K_CR, CR_STOP_NODMA);
    qtest_outb(s, NE2K_ISR, 0x7f);
    qtest_outb(s, NE2K_RBCR0, 0);
    qtest_outb(s, NE2K_RBCR1, 0);
    qtest_outb(s, NE2K_IMR, ISR_RDC);
    qtest_outb(s, NE2K_CR, CR_START | CR_REMOTE_READ);

    g_assert_cmphex(qtest_inb(s, NE2K_ISR), ==, ISR_RDC);
    g_assert_true(qtest_get_irq(s, NE2K_IRQ));

    qtest_inb(s, NE2K_RESET);
    g_assert_cmphex(qtest_inb(s, NE2K_ISR), ==, ISR_RST);
    g_assert_false(qtest_get_irq(s, NE2K_IRQ));
    qtest_outb(s, NE2K_RESET, 0);

    qtest_quit(s);
}

static void test_bus_reset(void)
{
    const uint16_t base = 0x320;
    const unsigned irq = 10;
    QTestState *s = qtest_init("-machine pc -nodefaults "
                              "-device ne2k_isa,iobase=0x320,irq=10");

    qtest_irq_intercept_in(s, "ioapic");
    g_assert_cmphex(qtest_inb(s, base), ==, CR_STOP_NODMA);

    qtest_outb(s, base + 0x07, 0x7f);
    qtest_outb(s, base + 0x0a, 0);
    qtest_outb(s, base + 0x0b, 0);
    qtest_outb(s, base + 0x0f, ISR_RDC);
    qtest_outb(s, base, CR_START | CR_REMOTE_READ);
    g_assert_cmphex(qtest_inb(s, base + 0x07), ==, ISR_RDC);
    g_assert_true(qtest_get_irq(s, irq));

    qtest_system_reset(s);
    g_assert_cmphex(qtest_inb(s, base), ==, CR_STOP_NODMA);
    g_assert_cmphex(qtest_inb(s, base + 0x07), ==, ISR_RST);
    g_assert_false(qtest_get_irq(s, irq));

    /* DMA completion must remain masked until the driver enables it. */
    qtest_outb(s, base + 0x0a, 0);
    qtest_outb(s, base + 0x0b, 0);
    qtest_outb(s, base, CR_START | CR_REMOTE_READ);
    g_assert_cmphex(qtest_inb(s, base + 0x07), ==, ISR_RDC);
    g_assert_false(qtest_get_irq(s, irq));
    qtest_outb(s, base + 0x0f, ISR_RDC);
    g_assert_true(qtest_get_irq(s, irq));
    qtest_outb(s, base + 0x07, ISR_RDC);
    g_assert_false(qtest_get_irq(s, irq));

    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/ne2000/isa/reset-irq", test_reset_irq);
    qtest_add_func("/ne2000/isa/bus-reset", test_bus_reset);

    return g_test_run();
}
