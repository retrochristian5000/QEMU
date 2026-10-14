/*
 * Reproducible, rights-free RCA CED transport and descriptor tests.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced.h"

static CedMedia example_media(void)
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

static void test_descriptor(void)
{
    CedMedia m = example_media(), decoded = { 0 };
    uint8_t data[CED_DESCRIPTOR_SIZE];

    g_assert_true(ced_media_encode(&m, data));
    g_assert_cmpmem(data, 8, "WHP-CED1", 8);
    g_assert_true(ced_media_decode(data, sizeof(data), &decoded));
    g_assert_cmpint(decoded.video, ==, CED_VIDEO_NTSC);
    g_assert_cmpint(decoded.audio, ==, CED_AUDIO_MONO);
    g_assert_cmpint(decoded.daxi, ==, CED_DAXI_UNEXAMINED);
    g_assert_cmpuint(decoded.side_count, ==, 2);
    g_assert_cmpuint(decoded.side_fields[0], ==, 10000);
    g_assert_cmpuint(decoded.side_fields[1], ==, 12000);
    g_assert_false(ced_media_decode(data, sizeof(data) - 1, &decoded));
    g_assert_false(ced_media_decode(data, sizeof(data) + 1, &decoded));
    data[0] = 'L'; /* No LaserDisc or arbitrary raw movie identification. */
    g_assert_false(ced_media_decode(data, sizeof(data), &decoded));
    data[0] = 'W';
    data[13] = 1;
    g_assert_false(ced_media_decode(data, sizeof(data), &decoded));
    data[13] = 0;
    data[9] = 2; /* Unsupported PAL conversion cannot silently claim NTSC. */
    g_assert_false(ced_media_decode(data, sizeof(data), &decoded));
    data[9] = CED_VIDEO_NTSC;
    data[20] = 0; data[21] = 0; data[22] = 0; data[23] = 0;
    g_assert_false(ced_media_decode(data, sizeof(data), &decoded));

    m.side_count = 1;
    g_assert_false(ced_media_valid(&m));
    m.side_fields[1] = 0;
    g_assert_true(ced_media_valid(&m));
    g_assert_true(ced_media_encode(&m, data));
    g_assert_true(ced_media_decode(data, sizeof(data), &decoded));
    g_assert_cmpuint(decoded.side_count, ==, 1);
}

static void test_caddy_and_side(void)
{
    CedMedia m = example_media();
    CedPlayer p;

    ced_player_init(&p, CED_TRANSPORT_RCA_SFT100);
    g_assert_cmpint(p.state, ==, CED_EMPTY);
    g_assert_false(ced_player_play(&p));
    g_assert_false(ced_player_eject(&p));
    g_assert_false(ced_player_insert(&p, &m, 3));
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_false(ced_player_insert(&p, &m, 2));
    g_assert_true(ced_player_eject(&p));
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_cmpuint(p.side, ==, 1);
    g_assert_true(ced_player_play(&p));
    g_assert_false(ced_player_eject(&p));
    g_assert_true(ced_player_stop(&p));
    g_assert_true(ced_player_eject(&p));
    /* Changing physical sides requires removing/reinserting the caddy. */
    g_assert_true(ced_player_insert(&p, &m, 2));
    g_assert_cmpuint(p.side, ==, 2);
    g_assert_cmpuint(p.position_fields, ==, 0);
    g_assert_true(ced_player_eject(&p));
}

static void test_playback_and_pause(void)
{
    CedMedia m = example_media();
    CedPlayer p;

    ced_player_init(&p, CED_TRANSPORT_RCA_SFT100);
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_true(ced_player_play(&p));
    g_assert_cmpint(p.state, ==, CED_STARTING);
    g_assert_true(ced_player_motor_running(&p));
    g_assert_false(ced_player_stylus_engaged(&p));
    ced_player_step_fields(&p, 479);
    g_assert_cmpint(p.state, ==, CED_STARTING);
    ced_player_step_fields(&p, 1);
    g_assert_cmpint(p.state, ==, CED_PLAYING);
    g_assert_true(ced_player_stylus_engaged(&p));
    g_assert_true(ced_player_video_visible(&p));
    g_assert_true(ced_player_audio_audible(&p));
    ced_player_step_fields(&p, 100);
    g_assert_cmpuint(p.position_fields, ==, 100);
    g_assert_true(ced_player_pause(&p));
    g_assert_false(ced_player_video_visible(&p));
    g_assert_false(ced_player_audio_audible(&p));
    g_assert_false(ced_player_stylus_engaged(&p));
    ced_player_step_fields(&p, 100);
    g_assert_cmpuint(p.position_fields, ==, 100);
    g_assert_true(ced_player_play(&p));
    g_assert_cmpint(p.state, ==, CED_PLAYING);
    ced_player_step_fields(&p, 10);
    g_assert_cmpuint(p.position_fields, ==, 110);
}

static void test_visual_and_rapid_search(void)
{
    CedMedia m = example_media();
    CedPlayer p;

    ced_player_init(&p, CED_TRANSPORT_RCA_SFT100);
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_true(ced_player_play(&p));
    ced_player_step_fields(&p, 480);
    g_assert_true(ced_player_visual_search(&p));
    g_assert_true(ced_player_video_visible(&p));
    g_assert_false(ced_player_audio_audible(&p));
    ced_player_step_fields(&p, 2);
    g_assert_cmpuint(p.position_fields, ==, 32);
    g_assert_true(ced_player_rapid_seek(&p, 9999));
    g_assert_cmpint(p.state, ==, CED_RAPID_SEEK);
    g_assert_false(ced_player_stylus_engaged(&p));
    g_assert_false(ced_player_video_visible(&p));
    g_assert_false(ced_player_audio_audible(&p));
    ced_player_step_fields(&p, 1);
    g_assert_cmpuint(p.position_fields, ==, 9999);
    g_assert_cmpint(p.state, ==, CED_PAUSED);
    g_assert_false(ced_player_rapid_seek(&p, 10000));
    g_assert_true(ced_player_play(&p));
    ced_player_step_fields(&p, 1);
    g_assert_cmpint(p.state, ==, CED_END_OF_SIDE);
    g_assert_cmpuint(p.position_fields, ==, 10000);
    g_assert_false(ced_player_play(&p));
    g_assert_true(ced_player_eject(&p));
}

static void test_overflow_and_rf(void)
{
    CedMedia m = example_media();
    CedPlayer p;

    ced_player_init(&p, CED_TRANSPORT_RCA_SFT100);
    g_assert_cmpuint(p.rf_channel, ==, 3);
    g_assert_false(ced_player_set_rf_channel(&p, 5));
    g_assert_true(ced_player_set_rf_channel(&p, 4));
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_true(ced_player_play(&p));
    ced_player_step_fields(&p, UINT64_MAX);
    g_assert_cmpint(p.state, ==, CED_END_OF_SIDE);
    g_assert_cmpuint(p.position_fields, ==, 10000);
    /* Nominal spindle rate must not replace the rational TV field clock. */
    g_assert_cmpuint(CED_NTSC_FIELDS_PER_REV, ==, 8);
    g_assert_cmpuint(CED_NTSC_FIELD_RATE_NUM, ==, 60000);
    g_assert_cmpuint(CED_NTSC_FIELD_RATE_DEN, ==, 1001);
    g_assert_cmpuint(CED_NTSC_BURIED_CHROMA_HZ, !=,
                     CED_NTSC_OUTPUT_CHROMA_HZ);
    ced_player_init(&p, CED_TRANSPORT_GENERIC);
    g_assert_cmpuint(p.rf_channel, ==, 0);
    g_assert_false(ced_player_set_rf_channel(&p, 3));
    g_assert_true(ced_player_insert(&p, &m, 1));
    g_assert_true(ced_player_play(&p));
    g_assert_false(ced_player_visual_search(&p));
    g_assert_false(ced_player_rapid_seek(&p, 10));
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ced/descriptor", test_descriptor);
    g_test_add_func("/ced/caddy-side", test_caddy_and_side);
    g_test_add_func("/ced/play-pause", test_playback_and_pause);
    g_test_add_func("/ced/search", test_visual_and_rapid_search);
    g_test_add_func("/ced/clock-rf", test_overflow_and_rf);
    return g_test_run();
}
