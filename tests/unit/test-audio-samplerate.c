/*
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include "audio/audio_int.h"

static void test_stream(gconstpointer opaque)
{
    int rate_in = GPOINTER_TO_INT(opaque);
    const char *reason = NULL;
    AudioSamplerate *rate = audio_samplerate_new(rate_in, 48000, &reason);
    struct st_sample input[100] = {0};
    struct st_sample output[512] = {0};
    size_t consumed, produced;
    size_t expected = 100 * 48000 / rate_in;

    g_assert_nonnull(rate);
    for (size_t i = 0; i < G_N_ELEMENTS(input); i++) {
#ifdef FLOAT_MIXENG
        input[i].l = 0.25f;
#else
        input[i].l = INT32_MAX / 4;
#endif
    }

    /* Exercise partial writes with tiny output windows and a final drain. */
    for (int pass = 0; pass < 2; pass++) {
        consumed = produced = 0;
        memset(output, 0, sizeof(output));
        while (consumed < G_N_ELEMENTS(input)) {
            size_t ni = MIN((size_t)13, G_N_ELEMENTS(input) - consumed);
            size_t no = MIN((size_t)17, G_N_ELEMENTS(output) - produced);

            g_assert_cmpuint(no, >, 0);
            g_assert_cmpint(audio_samplerate_mix(rate, input + consumed, &ni,
                            output + produced, &no, false), ==, 0);
            g_assert_true(ni || no);
            consumed += ni;
            produced += no;
        }
        for (;;) {
            size_t ni = 0;
            size_t no = MIN((size_t)17, G_N_ELEMENTS(output) - produced);

            g_assert_cmpuint(no, >, 0);
            g_assert_cmpint(audio_samplerate_mix(rate, input, &ni,
                            output + produced, &no, true), ==, 0);
            g_assert_cmpuint(ni, ==, 0);
            produced += no;
            if (!no) {
                break;
            }
        }
        g_assert_cmpuint(produced, >=, expected);
        g_assert_cmpuint(produced, <=, expected + 1);
        for (size_t i = 0; i < produced; i++) {
            g_assert_true(output[i].r == 0);
        }
        g_assert_true(output[produced / 2].l > 0);
        g_assert_cmpint(audio_samplerate_reset(rate), ==, 0);
    }
    audio_samplerate_free(rate);
}

static void test_invalid(void)
{
    const char *reason = NULL;

    g_assert_null(audio_samplerate_new(0, 48000, &reason));
    g_assert_nonnull(reason);
    g_assert_null(audio_samplerate_new(1, 48000, &reason));
    g_assert_nonnull(reason);
}

int main(int argc, char **argv)
{
    g_test_init(&argc, &argv, NULL);
    g_test_add_data_func("/audio/samplerate/11025", GINT_TO_POINTER(11025),
                         test_stream);
    g_test_add_data_func("/audio/samplerate/22050", GINT_TO_POINTER(22050),
                         test_stream);
    g_test_add_data_func("/audio/samplerate/44100", GINT_TO_POINTER(44100),
                         test_stream);
    g_test_add_data_func("/audio/samplerate/96000", GINT_TO_POINTER(96000),
                         test_stream);
    g_test_add_func("/audio/samplerate/invalid", test_invalid);
    return g_test_run();
}
