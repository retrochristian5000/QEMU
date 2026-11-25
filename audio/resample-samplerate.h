/*
 * SPDX-License-Identifier: MIT
 */
#ifndef QEMU_RESAMPLE_SAMPLERATE_H
#define QEMU_RESAMPLE_SAMPLERATE_H

typedef struct AudioSamplerate AudioSamplerate;
struct st_sample;

AudioSamplerate *audio_samplerate_new(int inrate, int outrate,
                                     const char **reason);
void audio_samplerate_free(AudioSamplerate *rate);
size_t audio_samplerate_input_frames(const AudioSamplerate *rate,
                                    size_t output_frames);
int audio_samplerate_mix(AudioSamplerate *rate, const struct st_sample *input,
                         size_t *input_frames, struct st_sample *output,
                         size_t *output_frames, bool drain);
int audio_samplerate_reset(AudioSamplerate *rate);
const char *audio_samplerate_error(int error);

#endif
