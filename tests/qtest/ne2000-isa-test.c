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

typedef struct ResourceConflict {
    const char *args;
    const char *diagnostic;
} ResourceConflict;

static const ResourceConflict conflicts[] = {
    {
        "-device ne2k_isa,iobase=0x301,irq=9",
        "*NE2000 ISA I/O base 0x301 must be aligned to 0x20*",
    }, {
        "-device ne2k_isa,iobase=0x300,irq=2",
        "*NE2000 ISA IRQ 2 is unsupported*",
    }, {
        "-device ne2k_isa,iobase=0x300,irq=9 "
        "-device ne2k_isa,iobase=0x300,irq=10",
        "*ne2k_isa: ISA I/O range 0x300-0x31f overlaps*",
    }, {
        "-device ne2k_isa,iobase=0x60,irq=10",
        "*ne2k_isa: ISA I/O range 0x60-0x7f overlaps*",
    }, {
        /* The start is unassigned, but COM1 occupies the last 8 ports. */
        "-serial null -device ne2k_isa,iobase=0x3e0,irq=10",
        "*ne2k_isa: ISA I/O range 0x3e0-0x3ff overlaps*at port 0x3f8*",
    }, {
        /* Reverse the creation order: the UART must reject the collision. */
        "-device ne2k_isa,iobase=0x3e0,irq=10 "
        "-chardev null,id=uart -device isa-serial,index=0,chardev=uart",
        "*isa-serial: ISA I/O range 0x3f8-0x3ff overlaps*at port 0x3f8*",
    }, {
        "-chardev null,id=uart -device isa-serial,iobase=0x10000,chardev=uart",
        "*isa-serial: invalid ISA I/O range*",
    }, {
        "-chardev null,id=uart -device isa-serial,irq=16,chardev=uart",
        "*isa-serial: COM1 IRQ 16 is not connected on this bus*",
    }, {
        "-chardev null,id=a -device isa-serial,index=0,chardev=a "
        "-chardev null,id=b -device isa-serial,index=0,chardev=b",
        "*isa-serial: COM1 is already assigned*",
    },
};

static void test_resource_conflict(gconstpointer opaque)
{
    const ResourceConflict *test = opaque;

    if (g_test_subprocess()) {
        QTestState *s = qtest_initf("-M pc -nodefaults %s", test->args);

        qtest_quit(s);
        return;
    }
    g_test_trap_subprocess(NULL, 10 * G_USEC_PER_SEC, 0);
    g_test_trap_assert_failed();
    g_test_trap_assert_stderr(test->diagnostic);
}

static void test_unassigned_io_root(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                              "-device ne2k_isa,iobase=0x300,irq=10");

    /* Free ports resolve to the root I/O fallback, not another device. */
    g_assert_cmphex(qtest_inb(s, 0x2ff), ==, 0xff);
    g_assert_cmphex(qtest_inb(s, 0x320), ==, 0xff);
    g_assert_cmphex(qtest_inb(s, NE2K_CR), ==, CR_STOP_NODMA);
    g_assert_cmphex(qtest_inb(s, NE2K_ISR), ==, ISR_RST);
    qtest_quit(s);
}

static void test_separate_io_windows(void)
{
    QTestState *s = qtest_init("-M pc -nodefaults "
                              "-device ne2k_isa,iobase=0x300,irq=10 "
                              "-device ne2k_isa,iobase=0x320,irq=11");

    qtest_outb(s, 0x300, CR_STOP_NODMA);
    qtest_outb(s, 0x320, CR_STOP_NODMA);
    qtest_outb(s, 0x307, 0x7f);
    qtest_outb(s, 0x327, 0x7f);
    qtest_outb(s, 0x30a, 0);
    qtest_outb(s, 0x30b, 0);
    qtest_outb(s, 0x300, CR_START | CR_REMOTE_READ);
    g_assert_cmphex(qtest_inb(s, 0x307), ==, ISR_RDC);
    g_assert_cmphex(qtest_inb(s, 0x327), ==, ISR_RST);
    qtest_inb(s, 0x31f);
    g_assert_cmphex(qtest_inb(s, 0x307), ==, ISR_RST);
    g_assert_cmphex(qtest_inb(s, 0x320), ==, CR_STOP_NODMA);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/ne2000/isa/reset-irq", test_reset_irq);
    qtest_add_func("/ne2000/isa/bus-reset", test_bus_reset);
    qtest_add_func("/ne2000/isa/unassigned-io-root",
                   test_unassigned_io_root);
    qtest_add_func("/ne2000/isa/separate-io-windows",
                   test_separate_io_windows);
    for (unsigned i = 0; i < ARRAY_SIZE(conflicts); i++) {
        g_autofree char *name = g_strdup_printf(
            "/ne2000/isa/resource-conflict/%u", i);

        qtest_add_data_func(name, &conflicts[i], test_resource_conflict);
    }

    return g_test_run();
}
