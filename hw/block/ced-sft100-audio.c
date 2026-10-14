/* RCA SFT100 decoded audio buffer. FM demodulator will feed this in future.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "qemu/osdep.h"
#include "hw/block/ced-sft100-audio.h"

void ced_sft100_audio_reset(CedSft100Audio *audio)
{
    if (audio) {
        audio->read_pos = 0;
        audio->count = 0;
    }
}

void ced_sft100_audio_gate(CedSft100Audio *audio,
                           const CedSft100Control *control)
{
    if (audio && !ced_sft100_audio_audible(control)) {
        ced_sft100_audio_reset(audio);
    }
}

size_t ced_sft100_audio_feed(CedSft100Audio *audio,
                            const CedSft100Control *control,
                            const int16_t *samples, size_t frames)
{
    uint32_t write_pos;
    size_t accepted, first;

    if (!audio || !control || !samples || !frames ||
        !ced_sft100_audio_audible(control)) {
        return 0;
    }
    accepted = MIN(frames, CED_SFT100_PCM_CAPACITY - audio->count);
    write_pos = (audio->read_pos + audio->count) % CED_SFT100_PCM_CAPACITY;
    first = MIN(accepted, CED_SFT100_PCM_CAPACITY - write_pos);
    memcpy(&audio->fifo[write_pos], samples, first * sizeof(*samples));
    memcpy(audio->fifo, samples + first,
           (accepted - first) * sizeof(*samples));
    audio->count += accepted;
    return accepted;
}

size_t ced_sft100_audio_peek(const CedSft100Audio *audio,
                            const int16_t **samples)
{
    if (!audio || !samples || !audio->count) {
        return 0;
    }
    *samples = &audio->fifo[audio->read_pos];
    return MIN(audio->count, CED_SFT100_PCM_CAPACITY - audio->read_pos);
}

void ced_sft100_audio_consume(CedSft100Audio *audio, size_t frames)
{
    size_t used;

    if (!audio) {
        return;
    }
    used = MIN(frames, audio->count);
    audio->read_pos = (audio->read_pos + used) % CED_SFT100_PCM_CAPACITY;
    audio->count -= used;
}
