/*
 * S-Video Y/C and composite physical input validation.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/display/analog-video.h"

static const AnalogVideoReceiverCaps ntsc = {
    .scan_mask = ANALOG_VIDEO_SCAN_BIT(ANALOG_VIDEO_SCAN_525_59_94),
    .color_mask = ANALOG_VIDEO_COLOR_BIT(ANALOG_VIDEO_COLOR_NTSC_358),
};
static const AnalogVideoReceiverCaps pal = {
    .scan_mask = ANALOG_VIDEO_SCAN_BIT(ANALOG_VIDEO_SCAN_625_50),
    .color_mask = ANALOG_VIDEO_COLOR_BIT(ANALOG_VIDEO_COLOR_PAL_443),
};

static AnalogVideoBaseband source(AnalogVideoConnection connection,
                                  uint32_t wires, AnalogVideoSignal signal)
{
    AnalogVideoBaseband s = {
        .connection = connection, .wires = wires, .signal = signal,
    };
    return s;
}

static void test_connectors(void)
{
    AnalogVideoBaseband s =
        source(ANALOG_VIDEO_CONNECTION_SVIDEO,
               ANALOG_VIDEO_WIRE_Y | ANALOG_VIDEO_WIRE_C,
               analog_video_ntsc_525_59_94);

    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_COLOR);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_COMPOSITE,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s = source(ANALOG_VIDEO_CONNECTION_COMPOSITE, ANALOG_VIDEO_WIRE_CVBS,
               analog_video_ntsc_525_59_94);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_COMPOSITE,
                                              &s), ==, ANALOG_VIDEO_LOCK_COLOR);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
}

static void test_missing_y_or_c(void)
{
    AnalogVideoBaseband s = source(ANALOG_VIDEO_CONNECTION_SVIDEO,
                                  ANALOG_VIDEO_WIRE_Y,
                                  analog_video_ntsc_525_59_94);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_LUMA);
    s.wires = ANALOG_VIDEO_WIRE_C;
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s.wires = 0;
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s.connection = ANALOG_VIDEO_CONNECTION_COMPOSITE;
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_COMPOSITE,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
}

static void test_invalid_wiring(void)
{
    AnalogVideoBaseband s = source(ANALOG_VIDEO_CONNECTION_SVIDEO,
                                  ANALOG_VIDEO_WIRE_Y | ANALOG_VIDEO_WIRE_CVBS,
                                  analog_video_ntsc_525_59_94);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s = source(ANALOG_VIDEO_CONNECTION_COMPOSITE,
               ANALOG_VIDEO_WIRE_CVBS | ANALOG_VIDEO_WIRE_C,
               analog_video_ntsc_525_59_94);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_COMPOSITE,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s.wires = ANALOG_VIDEO_WIRE_CVBS;
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_NONE,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION__MAX,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_COMPOSITE,
                                              NULL), ==, ANALOG_VIDEO_LOCK_NONE);
}

static void test_color_is_independent(void)
{
    AnalogVideoBaseband s = source(ANALOG_VIDEO_CONNECTION_SVIDEO,
                                  ANALOG_VIDEO_WIRE_Y | ANALOG_VIDEO_WIRE_C,
                                  analog_video_ntsc_525_59_94);
    g_assert_cmpint(analog_video_baseband_lock(&pal,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_NONE);
    s.signal = analog_video_pal_625_50;
    g_assert_cmpint(analog_video_baseband_lock(&pal,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_COLOR);
    s.signal = analog_video_pal_m_525_59_94;
    g_assert_cmpint(analog_video_baseband_lock(&ntsc,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_LUMA);
    s.signal = analog_video_pal_n_625_50;
    g_assert_cmpint(analog_video_baseband_lock(&pal,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_LUMA);
    s.signal.color = ANALOG_VIDEO_COLOR_MONOCHROME;
    g_assert_cmpint(analog_video_baseband_lock(&pal,
                                              ANALOG_VIDEO_CONNECTION_SVIDEO,
                                              &s), ==, ANALOG_VIDEO_LOCK_LUMA);
}

static void test_standard_controls(void)
{
    uint64_t num, den;
    g_assert_true(analog_video_get_line_rate(ANALOG_VIDEO_SCAN_525_59_94,
                                             &num, &den));
    g_assert_cmpuint(num, ==, 31500000);
    g_assert_cmpuint(den, ==, 2002);
    g_assert_true(analog_video_get_line_rate(ANALOG_VIDEO_SCAN_625_50,
                                             &num, &den));
    g_assert_cmpuint(num, ==, 31250);
    g_assert_cmpuint(den, ==, 2);
    g_assert_cmpint(ANALOG_SVIDEO_PIN_Y_GROUND, ==, 1);
    g_assert_cmpint(ANALOG_SVIDEO_PIN_C_GROUND, ==, 2);
    g_assert_cmpint(ANALOG_SVIDEO_PIN_Y, ==, 3);
    g_assert_cmpint(ANALOG_SVIDEO_PIN_C, ==, 4);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/analog-video/connection", test_connectors);
    g_test_add_func("/analog-video/luma-chroma", test_missing_y_or_c);
    g_test_add_func("/analog-video/invalid", test_invalid_wiring);
    g_test_add_func("/analog-video/colour-profile", test_color_is_independent);
    g_test_add_func("/analog-video/timing-pinout", test_standard_controls);
    return g_test_run();
}
