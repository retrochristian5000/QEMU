/* RCA SFT100 post-FM-decoder mono audio bridge (not a CED groove decoder).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_BLOCK_CED_SFT100_AUDIO_H
#define HW_BLOCK_CED_SFT100_AUDIO_H

#include "hw/block/ced-sft100-control.h"
#include <stddef.h>
#include <stdint.h>

/* Host-side PCM contract. Neither number describes on-disc FM modulation. */
#define CED_SFT100_PCM_RATE 48000U
#define CED_SFT100_PCM_CAPACITY 4096U

typedef struct CedSft100Audio {
    int16_t fifo[CED_SFT100_PCM_CAPACITY];
    uint32_t read_pos;
    uint32_t count;
} CedSft100Audio;

void ced_sft100_audio_reset(CedSft100Audio *audio);
/* Samples must be *already FM-demodulated* and mono/resampled to 48 kHz. */
size_t ced_sft100_audio_feed(CedSft100Audio *audio,
                            const CedSft100Control *control,
                            const int16_t *samples, size_t frames);
/* Returns the first contiguous run; valid until the FIFO is modified. */
size_t ced_sft100_audio_peek(const CedSft100Audio *audio,
                            const int16_t **samples);
void ced_sft100_audio_consume(CedSft100Audio *audio, size_t frames);
/* Pause, search, seek, stop and side-end discard stale decoded samples. */
void ced_sft100_audio_gate(CedSft100Audio *audio,
                           const CedSft100Control *control);

#endif
