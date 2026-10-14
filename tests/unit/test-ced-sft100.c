/*
 * RCA SFT100 device-independent controls and field clock regression tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced-sft100-control.h"

static CedMedia test_disc(void)
{
    CedMedia m = {
        .video = CED_VIDEO_NTSC,
        .audio = CED_AUDIO_MONO,
        .daxi = CED_DAXI_UNEXAMINED,
        .side_count = 2,
        .side_fields = { 10000, 12000 },
    };
    return m;
}

static void test_lever_and_caddy(void)
{
    CedSft100Control s;
    CedMedia m = test_disc();

    ced_sft100_control_init(&s);
    g_assert_cmpint(s.lever, ==, CED_SFT100_OFF);
    g_assert_cmpint(ced_sft100_rf_source(&s), ==, CED_SFT100_RF_ANTENNA);
    g_assert_false(ced_sft100_insert(&s, &m, 1));
    g_assert_false(ced_sft100_set_lever(&s, (CedSft100Lever)7));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_cmpint(ced_sft100_rf_source(&s), ==, CED_SFT100_RF_PLAYER);
    g_assert_true(ced_sft100_insert(&s, &m, 1));
    g_assert_false(ced_sft100_insert(&s, &m, 2));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_PLAY));
    g_assert_cmpint(s.player.state, ==, CED_STARTING);
    g_assert_false(ced_sft100_remove(&s));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_OFF));
    g_assert_false(ced_sft100_remove(&s));
    g_assert_cmpint(s.player.state, ==, CED_RETAINED);
    g_assert_cmpuint(s.player.side, ==, 1);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_remove(&s));
    g_assert_true(ced_sft100_insert(&s, &m, 2));
    g_assert_cmpuint(s.player.side, ==, 2);
    g_assert_true(ced_sft100_remove(&s));
}

static void test_playback_clock_pause(void)
{
    CedSft100Control s;
    CedMedia m = test_disc();

    ced_sft100_control_init(&s);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_insert(&s, &m, 1));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_PLAY));
    g_assert_true(ced_sft100_clock_active(&s));
    g_assert_true(ced_sft100_motor_running(&s));
    g_assert_false(ced_sft100_audio_audible(&s));
    g_assert_false(ced_sft100_video_visible(&s));
    /* Exactly 480 NTSC fields in 8.008 seconds. */
    ced_sft100_advance_ns(&s, UINT64_C(8008000000));
    g_assert_cmpint(s.player.state, ==, CED_PLAYING);
    g_assert_cmpuint(s.player.position_fields, ==, 0);
    g_assert_true(ced_sft100_video_visible(&s));
    g_assert_true(ced_sft100_audio_audible(&s));
    /* Exactly 60 fields in 1.001 seconds; no float rounding drift. */
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 60);
    g_assert_true(ced_sft100_pause_toggle(&s));
    g_assert_cmpint(s.player.state, ==, CED_PAUSED);
    g_assert_false(ced_sft100_clock_active(&s));
    g_assert_false(ced_sft100_video_visible(&s));
    g_assert_false(ced_sft100_audio_audible(&s));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 60);
    g_assert_true(ced_sft100_pause_toggle(&s));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 120);
}

static void test_visual_search_reverse(void)
{
    CedSft100Control s;
    CedMedia m = test_disc();

    ced_sft100_control_init(&s);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_insert(&s, &m, 1));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_PLAY));
    ced_sft100_advance_ns(&s, UINT64_C(8008000000));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_true(ced_sft100_search(&s, true));
    g_assert_false(ced_sft100_audio_audible(&s));
    g_assert_true(ced_sft100_video_visible(&s));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 1020);
    g_assert_true(ced_sft100_search_release(&s));
    g_assert_true(ced_sft100_search(&s, false));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 60);
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 0);
    g_assert_cmpint(s.player.state, ==, CED_PAUSED);
    g_assert_false(ced_sft100_video_visible(&s));
}

static void test_rapid_and_end(void)
{
    CedSft100Control s;
    CedMedia m = test_disc();

    ced_sft100_control_init(&s);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_insert(&s, &m, 1));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_PLAY));
    g_assert_false(ced_sft100_rapid_access(&s, 10000));
    g_assert_false(ced_sft100_rapid_access(&s, 20)); /* startup */
    ced_sft100_advance_ns(&s, UINT64_C(8008000000));
    g_assert_true(ced_sft100_rapid_access(&s, 9999));
    g_assert_false(ced_sft100_video_visible(&s));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpuint(s.player.position_fields, ==, 9999);
    g_assert_cmpint(s.player.state, ==, CED_PAUSED);
    g_assert_true(ced_sft100_pause_toggle(&s));
    ced_sft100_advance_ns(&s, UINT64_C(1001000000));
    g_assert_cmpint(s.player.state, ==, CED_END_OF_SIDE);
    g_assert_cmpuint(s.player.position_fields, ==, 10000);
    g_assert_false(ced_sft100_audio_audible(&s));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_remove(&s));
}

static void test_clock_limits(void)
{
    CedSft100Control s;
    CedMedia m = test_disc();

    ced_sft100_control_init(&s);
    g_assert_true(ced_sft100_select_channel(&s, 4));
    g_assert_false(ced_sft100_select_channel(&s, 12));
    g_assert_cmpuint(s.player.rf_channel, ==, 4);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_insert(&s, &m, 1));
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_PLAY));
    ced_sft100_advance_ns(&s, 10000000); /* 10ms < a field */
    g_assert_cmpint(s.player.state, ==, CED_STARTING);
    g_assert_cmpuint(s.player.start_remaining_fields, ==, 480);
    ced_sft100_advance_ns(&s, UINT64_MAX);
    g_assert_cmpint(s.player.state, ==, CED_END_OF_SIDE);
    g_assert_cmpuint(s.player.position_fields, ==, 10000);
    g_assert_false(ced_sft100_clock_active(&s));
    g_assert_cmpuint(s.field_phase, ==, 0);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ced/sft100/lever-caddy", test_lever_and_caddy);
    g_test_add_func("/ced/sft100/clock-pause", test_playback_clock_pause);
    g_test_add_func("/ced/sft100/visual-reverse", test_visual_search_reverse);
    g_test_add_func("/ced/sft100/rapid-end", test_rapid_and_end);
    g_test_add_func("/ced/sft100/clock-limits", test_clock_limits);
    return g_test_run();
}
