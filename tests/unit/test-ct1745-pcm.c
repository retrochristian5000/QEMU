/* SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "hw/audio/ct1745-mixer.h"

static int16_t sample(const uint8_t *p)
{
    return (int16_t)lduw_le_p(p);
}

static void test_formats(void)
{
    uint8_t regs[256] = { 0 };
    uint8_t out[16];
    const uint8_t u8[] = { 0, 128, 255 };
    const uint8_t s8[] = { 0x80, 0x7f };
    const uint8_t s16[] = { 0, 0x80, 0xff, 0x7f };
    const uint8_t u16[] = { 0, 0, 0xff, 0xff };

    memset(regs + 0x30, 0xf8, 4);
    g_assert_cmpuint(ct1745_pcm_render(regs, u8, 3, false, false, false,
                                      out), ==, 12);
    g_assert_cmpint(sample(out), ==, -32768);
    g_assert_cmpint(sample(out + 2), ==, -32768);
    g_assert_cmpint(sample(out + 4), ==, 0);
    g_assert_cmpint(sample(out + 6), ==, 0);
    g_assert_cmpint(sample(out + 8), ==, 32512);
    g_assert_cmpint(sample(out + 10), ==, 32512);
    ct1745_pcm_render(regs, s8, 1, false, true, true, out);
    g_assert_cmpint(sample(out), ==, -32768);
    g_assert_cmpint(sample(out + 2), ==, 32512);
    ct1745_pcm_render(regs, s16, 1, true, true, true, out);
    g_assert_cmpint(sample(out), ==, -32768);
    g_assert_cmpint(sample(out + 2), ==, 32767);
    ct1745_pcm_render(regs, u16, 1, true, false, true, out);
    g_assert_cmpint(sample(out), ==, -32768);
    g_assert_cmpint(sample(out + 2), ==, 32767);
}

static void test_gain(void)
{
    uint8_t regs[256] = { 0 };
    uint8_t out[4];
    const uint8_t src[] = { 0x00, 0x40 };

    ct1745_reset(regs);
    ct1745_pcm_render(regs, src, 1, true, true, false, out);
    /* Reset voice and master each attenuate by 14 dB. */
    g_assert_cmpint(sample(out), ==, 652);
    g_assert_cmpint(sample(out + 2), ==, 652);
    g_assert_true(ct1745_write(regs, 0x30, 0xf8));
    g_assert_true(ct1745_write(regs, 0x32, 0xf8));
    ct1745_pcm_render(regs, src, 1, true, true, false, out);
    g_assert_cmpint(sample(out), ==, 16384);
    g_assert_cmpint(sample(out + 2), ==, 652);
    g_assert_true(ct1745_write(regs, 0x41, 0xc0));
    ct1745_pcm_render(regs, src, 1, true, true, false, out);
    g_assert_cmpint(sample(out), ==, 32767);
    g_assert_cmpint(sample(out + 2), ==, 652);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ct1745/pcm/formats", test_formats);
    g_test_add_func("/ct1745/pcm/gain", test_gain);
    return g_test_run();
}
