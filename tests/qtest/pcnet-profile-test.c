/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "libqtest.h"

#define PCNET_CONFIG 0x80002000U
#define PCNET_IO 0xc000

static void config_write(QTestState *qts, unsigned reg, uint32_t value)
{
    qtest_outl(qts, 0xcf8, PCNET_CONFIG | reg);
    qtest_outl(qts, 0xcfc, value);
}

static uint32_t config_read(QTestState *qts, unsigned reg)
{
    qtest_outl(qts, 0xcf8, PCNET_CONFIG | reg);
    return qtest_inl(qts, 0xcfc);
}

static void csr_write(QTestState *qts, unsigned reg, uint16_t value)
{
    qtest_outw(qts, PCNET_IO + 0x12, reg);
    qtest_outw(qts, PCNET_IO + 0x10, value);
}

static uint16_t csr_read(QTestState *qts, unsigned reg)
{
    qtest_outw(qts, PCNET_IO + 0x12, reg);
    return qtest_inw(qts, PCNET_IO + 0x10);
}

static void test_am79c970a(gconstpointer opaque)
{
    bool explicit = GPOINTER_TO_INT(opaque);
    QTestState *qts = qtest_initf("-M pc -nodefaults "
                                 "-device %s,addr=4,romfile=",
                                 explicit ? "am79c970a-pci" : "pcnet");

    g_assert_cmphex(config_read(qts, 0), ==, 0x20001022);
    config_write(qts, 0x10, UINT32_MAX);
    g_assert_cmphex(config_read(qts, 0x10), ==, 0xffffffe1);
    config_write(qts, 0x14, UINT32_MAX);
    g_assert_cmphex(config_read(qts, 0x14), ==, 0xffffffe0);
    config_write(qts, 0x10, PCNET_IO | 1);
    config_write(qts, 0x14, 0xe0000000);
    config_write(qts, 4, 1);

    g_assert_cmphex(csr_read(qts, 88), ==, 0x1003);
    g_assert_cmphex(csr_read(qts, 89), ==, 0x0262);
    g_assert_cmphex(csr_read(qts, 100), ==, explicit ? 0x0600 : 0x0200);
    if (explicit) {
        config_write(qts, 0x40, UINT32_MAX);
        g_assert_cmphex(config_read(qts, 0x40), ==, 0);
        csr_write(qts, 100, 0x1234);
        g_assert_cmphex(csr_read(qts, 100), ==, 0x1234);
        qtest_inw(qts, PCNET_IO + 0x14);
        g_assert_cmphex(csr_read(qts, 100), ==, 0x0600);

        csr_write(qts, 47, 0x000f);
        g_assert_cmphex(csr_read(qts, 47), ==, 0);
        csr_write(qts, 46, 0);
        /* Disable receiver and transmitter; exercise only the counter. */
        csr_write(qts, 15, 3);
        csr_write(qts, 0, 2);
        qtest_clock_step(qts, 300);
        g_assert_cmpuint(csr_read(qts, 46), ==, 10);
        qtest_clock_step(qts, 300);
        g_assert_cmpuint(csr_read(qts, 46), ==, 20);
        csr_write(qts, 0, 4);
    }
    qtest_quit(qts);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_data_func("/pcnet/profile/legacy", GINT_TO_POINTER(0),
                        test_am79c970a);
    qtest_add_data_func("/pcnet/profile/am79c970a", GINT_TO_POINTER(1),
                        test_am79c970a);
    return g_test_run();
}
