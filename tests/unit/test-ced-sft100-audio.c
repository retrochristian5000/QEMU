/* CED mono decoded PCM FIFO regression tests. */
#include "qemu/osdep.h"
#include "hw/block/ced-sft100-audio.h"

static CedMedia mono_disc(void)
{
    CedMedia m = { .video = CED_VIDEO_NTSC, .audio = CED_AUDIO_MONO,
                   .side_count = 1, .side_fields = { 6000, 0 } };
    return m;
}

static void start(CedSft100Control *s)
{
    CedMedia m = mono_disc();
    ced_sft100_control_init(s);
    g_assert_true(ced_sft100_set_lever(s, CED_SFT100_LOAD_UNLOAD));
    g_assert_true(ced_sft100_insert(s, &m, 1));
    g_assert_true(ced_sft100_set_lever(s, CED_SFT100_PLAY));
    ced_sft100_advance_ns(s, UINT64_C(8008000000));
    g_assert_true(ced_sft100_audio_audible(s));
}

static void test_queue(void)
{
    CedSft100Control s;
    CedSft100Audio a = { 0 };
    int16_t src[] = { 1, 2, 3, 4, 5 };
    const int16_t *p = NULL;

    start(&s);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 5), ==, 5);
    g_assert_cmpuint(a.count, ==, 5);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &p), ==, 5);
    g_assert_cmpint(p[0], ==, 1);
    g_assert_cmpint(p[4], ==, 5);
    ced_sft100_audio_consume(&a, 2);
    g_assert_cmpuint(a.count, ==, 3);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &p), ==, 3);
    g_assert_cmpint(p[0], ==, 3);
    ced_sft100_audio_consume(&a, SIZE_MAX);
    g_assert_cmpuint(a.count, ==, 0);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &p), ==, 0);
}

static void test_wrap_and_full(void)
{
    CedSft100Control s;
    CedSft100Audio a = { 0 };
    int16_t src[CED_SFT100_PCM_CAPACITY];
    const int16_t *p = NULL;

    start(&s);
    for (unsigned i = 0; i < CED_SFT100_PCM_CAPACITY; i++) {
        src[i] = i;
    }
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 4096), ==, 4096);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 1), ==, 0);
    ced_sft100_audio_consume(&a, 4094);
    g_assert_cmpuint(a.count, ==, 2);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 4), ==, 4);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &p), ==, 2);
    g_assert_cmpint(p[0], ==, 4094);
    ced_sft100_audio_consume(&a, 2);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &p), ==, 4);
    g_assert_cmpint(p[0], ==, 0);
    g_assert_cmpint(p[3], ==, 3);
}

static void test_mute_and_restart(void)
{
    CedSft100Control s;
    CedSft100Audio a = { 0 };
    int16_t src[] = { 0x1234, -100 };

    start(&s);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 2), ==, 2);
    g_assert_true(ced_sft100_pause_toggle(&s));
    ced_sft100_audio_gate(&a, &s);
    g_assert_cmpuint(a.count, ==, 0);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 2), ==, 0);
    g_assert_true(ced_sft100_pause_toggle(&s));
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 2), ==, 2);
    g_assert_true(ced_sft100_search(&s, true));
    ced_sft100_audio_gate(&a, &s);
    g_assert_cmpuint(a.count, ==, 0);
    g_assert_true(ced_sft100_search_release(&s));
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 2), ==, 2);
    g_assert_true(ced_sft100_set_lever(&s, CED_SFT100_OFF));
    ced_sft100_audio_gate(&a, &s);
    g_assert_cmpuint(a.count, ==, 0);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, src, 2), ==, 0);
}

static void test_null_and_no_output(void)
{
    CedSft100Control s = { 0 };
    CedSft100Audio a = { 0 };
    int16_t src = 17;
    const int16_t *samples = NULL;

    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, &src, 1), ==, 0);
    start(&s);
    g_assert_cmpuint(ced_sft100_audio_feed(NULL, &s, &src, 1), ==, 0);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, NULL, &src, 1), ==, 0);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, NULL, 1), ==, 0);
    g_assert_cmpuint(ced_sft100_audio_feed(&a, &s, &src, 0), ==, 0);
    g_assert_cmpuint(ced_sft100_audio_peek(&a, &samples), ==, 0);
    ced_sft100_audio_consume(NULL, 5);
    ced_sft100_audio_reset(NULL);
    ced_sft100_audio_gate(NULL, NULL);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_func("/ced/sft100/audio-queue", test_queue);
    g_test_add_func("/ced/sft100/audio-wrap", test_wrap_and_full);
    g_test_add_func("/ced/sft100/audio-muting", test_mute_and_restart);
    g_test_add_func("/ced/sft100/audio-null", test_null_and_no_output);
    return g_test_run();
}
