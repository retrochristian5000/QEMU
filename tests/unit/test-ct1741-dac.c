/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/audio/ct1741-dsp.h"

static void test_hold(void)
{
    CT1741DAC dac;
    const uint8_t *data;

    ct1741_dac_reset(&dac, 0, 0x40);
    ct1741_dac_write(&dac, 1000000, 0xc0);
    g_assert_cmpuint(ct1741_dac_peek(&dac, &data), ==, 44);
    for (size_t i = 0; i < 44; i++) {
        g_assert_cmphex(data[i], ==, 0x40);
    }
    ct1741_dac_consume(&dac, 44);
    ct1741_dac_advance(&dac, 10000000);
    g_assert_cmpuint(ct1741_dac_peek(&dac, &data), ==, 397);
    for (size_t i = 0; i < 397; i++) {
        g_assert_cmphex(data[i], ==, 0xc0);
    }
    g_assert_cmpuint(dac.remainder, ==, 0);
    ct1741_dac_consume(&dac, 397);
    g_assert_cmpuint(dac.count, ==, 0);
}

static void test_capacity(void)
{
    CT1741DAC dac;
    const uint8_t *data;
    size_t frames;

    ct1741_dac_reset(&dac, 0, 0x12);
    ct1741_dac_advance(&dac, 100000000);
    ct1741_dac_consume(&dac, 3000);
    ct1741_dac_write(&dac, 100000000, 0x34);
    ct1741_dac_advance(&dac, 10000000000LL);
    g_assert_cmpuint(dac.count, ==, CT1741_DAC_CAPACITY);
    while ((frames = ct1741_dac_peek(&dac, &data))) {
        for (size_t i = 0; i < frames; i++) {
            g_assert_cmphex(data[i], ==, 0x34);
        }
        ct1741_dac_consume(&dac, frames);
    }
    ct1741_dac_reset(&dac, 10000000000LL, 0x80);
    g_assert_cmpuint(dac.count, ==, 0);
    g_assert_cmpuint(dac.remainder, ==, 0);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ct1741/dac/hold", test_hold);
    g_test_add_func("/ct1741/dac/capacity", test_capacity);
    return g_test_run();
}
