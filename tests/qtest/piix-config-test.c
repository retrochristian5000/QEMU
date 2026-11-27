/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "libqtest.h"

#define PIIX3_CONFIG 0x80000800U

static uint32_t config_read(QTestState *s, unsigned offset)
{
    qtest_outl(s, 0xcf8, PIIX3_CONFIG | offset);
    return qtest_inl(s, 0xcfc);
}

static void config_write(QTestState *s, unsigned offset, uint32_t value)
{
    qtest_outl(s, 0xcf8, PIIX3_CONFIG | offset);
    qtest_outl(s, 0xcfc, value);
}

static void test_piix3_header(void)
{
    QTestState *s = qtest_init("-M pc,x-south-bridge=piix3 -nodefaults");

    g_assert_cmphex(config_read(s, 0), ==, 0x70008086);
    g_assert_cmphex(config_read(s, 8) >> 8, ==, 0x060100);
    g_assert_cmphex(config_read(s, 0x0c), ==, 0x00800000);
    g_assert_cmphex(config_read(s, 4), ==, 0x02000007);

    /* Decode and bus-master bits cannot be disabled on function zero. */
    config_write(s, 4, 0);
    g_assert_cmphex(config_read(s, 4), ==, 0x02000007);
    config_write(s, 4, UINT32_MAX);
    g_assert_cmphex(config_read(s, 4), ==, 0x0200010f);

    /* Reserved fields cannot acquire fake resources or subsystem IDs. */
    config_write(s, 0x0c, UINT32_MAX);
    g_assert_cmphex(config_read(s, 0x0c), ==, 0x00800000);
    for (unsigned offset = 0x10; offset < 0x4c; offset += 4) {
        config_write(s, offset, UINT32_MAX);
        g_assert_cmphex(config_read(s, offset), ==, 0);
    }

    /* PIRQ controls remain independent of the standard header. */
    config_write(s, 0x60, 0x80800b0a);
    g_assert_cmphex(config_read(s, 0x60), ==, 0x80800b0a);
    config_write(s, 4, 0);
    g_assert_cmphex(config_read(s, 0x60), ==, 0x80800b0a);
    qtest_system_reset(s);
    g_assert_cmphex(config_read(s, 4), ==, 0x02000007);
    g_assert_cmphex(config_read(s, 0x60), ==, 0x80808080);
    qtest_quit(s);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    qtest_add_func("/piix/config/piix3-header", test_piix3_header);
    return g_test_run();
}
