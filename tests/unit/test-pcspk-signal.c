/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "hw/audio/pcspk-signal.h"

static void test_refresh(void)
{
    g_assert_cmphex(pcspk_refresh_bit(0), ==, 0);
    g_assert_cmphex(pcspk_refresh_bit(14999), ==, 0);
    g_assert_cmphex(pcspk_refresh_bit(15000), ==, 0x10);
    g_assert_cmphex(pcspk_refresh_bit(29999), ==, 0x10);
    g_assert_cmphex(pcspk_refresh_bit(30000), ==, 0);
}

static void test_waveform(void)
{
    const uint32_t rate = 32000, clocks = 1193182;

    for (uint32_t count = 75; count <= 65536; count++) {
        uint32_t period = rate * count;
        uint32_t high = ((count + 1) / 2) * rate;
        uint32_t phase = pcspk_advance_phase(0, period, clocks, 1792);

        g_assert_cmpuint(pcspk_square_sample(0, count, rate), ==, 160);
        g_assert_cmpuint(pcspk_square_sample(high - 1, count, rate), ==, 160);
        g_assert_cmpuint(pcspk_square_sample(high, count, rate), ==, 96);
        g_assert_cmpuint(pcspk_square_sample(period - 1, count, rate), ==, 96);
        g_assert_cmpuint(phase, <, period);
        g_assert_cmpuint(phase, ==, pcspk_advance_phase(
            pcspk_advance_phase(0, period, clocks, 613), period, clocks, 1179));
    }
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/pcspk/refresh", test_refresh);
    g_test_add_func("/pcspk/waveform", test_waveform);
    return g_test_run();
}
