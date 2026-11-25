/*
 * Optional streaming sample-rate conversion for host playback.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include <samplerate.h>
#include <math.h>
#include "audio_int.h"

#define SRC_CHUNK_FRAMES 512
#define PCM_SCALE 2147483648.0

struct AudioSamplerate {
    SRC_STATE *state;
    double ratio;
};

AudioSamplerate *audio_samplerate_new(int inrate, int outrate,
                                     const char **reason)
{
    AudioSamplerate *rate;
    double ratio;
    int err = 0;

    if (inrate <= 0 || outrate <= 0) {
        *reason = "invalid sample rate";
        return NULL;
    }
    ratio = (double)outrate / inrate;
    if (!src_is_valid_ratio(ratio)) {
        *reason = "unsupported sample-rate ratio";
        return NULL;
    }

    rate = g_new0(AudioSamplerate, 1);
    rate->state = src_new(SRC_SINC_FASTEST, 2, &err);
    if (!rate->state) {
        *reason = audio_samplerate_error(err);
        g_free(rate);
        return NULL;
    }
    rate->ratio = ratio;
    return rate;
}

void audio_samplerate_free(AudioSamplerate *rate)
{
    if (rate) {
        src_delete(rate->state);
        g_free(rate);
    }
}

const char *audio_samplerate_error(int error)
{
    const char *message = src_strerror(error);

    return message ? message : "unknown converter error";
}

int audio_samplerate_reset(AudioSamplerate *rate)
{
    return src_reset(rate->state);
}

size_t audio_samplerate_input_frames(const AudioSamplerate *rate,
                                    size_t output_frames)
{
    /* Advisory budget only: the converter reports the actual consumption. */
    return (size_t)MIN(ceil(output_frames / rate->ratio), (double)UINT32_MAX);
}

/*
 * The fixed-point mixer uses a signed 32-bit PCM scale in int64_t
 * accumulators. Do not clip sinc overshoot before the final mixer clip.
 */
static float sample_to_float(double value)
{
#ifndef FLOAT_MIXENG
    value /= PCM_SCALE;
#endif
    return isfinite(value) ? value : 0.0f;
}

static void mix_float(struct st_sample *dst, const float *src)
{
#ifdef FLOAT_MIXENG
    dst->l += src[0];
    dst->r += src[1];
#else
    /*
     * A single voice is normally within +/-1. Preserve filter overshoot,
     * but bound exceptional values before integer conversion.
     */
    dst->l += (int64_t)(CLAMP((double)src[0], -16.0, 16.0) * PCM_SCALE);
    dst->r += (int64_t)(CLAMP((double)src[1], -16.0, 16.0) * PCM_SCALE);
#endif
}

int audio_samplerate_mix(AudioSamplerate *rate, const struct st_sample *input,
                         size_t *input_frames, struct st_sample *output,
                         size_t *output_frames, bool drain)
{
    float in[SRC_CHUNK_FRAMES * 2];
    float out[SRC_CHUNK_FRAMES * 2];
    size_t consumed = 0, produced = 0;
    size_t in_max = *input_frames, out_max = *output_frames;
    int err = 0;

    while (produced < out_max) {
        size_t ni = MIN(in_max - consumed, SRC_CHUNK_FRAMES);
        size_t no = MIN(out_max - produced, SRC_CHUNK_FRAMES);
        SRC_DATA data = {
            .data_in = in,
            .data_out = out,
            .input_frames = ni,
            .output_frames = no,
            .end_of_input = drain && ni == in_max - consumed,
            .src_ratio = rate->ratio,
        };

        for (size_t i = 0; i < ni; i++) {
            in[2 * i] = sample_to_float(input[consumed + i].l);
            in[2 * i + 1] = sample_to_float(input[consumed + i].r);
        }

        err = src_process(rate->state, &data);
        if (err) {
            break;
        }
        for (long i = 0; i < data.output_frames_gen; i++) {
            mix_float(&output[produced + i], &out[2 * i]);
        }
        consumed += data.input_frames_used;
        produced += data.output_frames_gen;

        if (!data.input_frames_used && !data.output_frames_gen) {
            break;
        }
    }
    *input_frames = consumed;
    *output_frames = produced;
    return err;
}
