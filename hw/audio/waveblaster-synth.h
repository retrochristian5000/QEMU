/*
 * Host-side Wave Blaster-compatible synthesis.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_WAVEBLASTER_SYNTH_H
#define HW_AUDIO_WAVEBLASTER_SYNTH_H

#include "qemu/audio.h"

typedef struct WaveBlasterSynth WaveBlasterSynth;

WaveBlasterSynth *waveblaster_synth_new(AudioBackend *be, const char *soundfont,
                                      const uint8_t *mixer_regs, Error **errp);
void waveblaster_synth_free(WaveBlasterSynth *s);
void waveblaster_synth_reset(WaveBlasterSynth *s);
void waveblaster_synth_write(WaveBlasterSynth *s, uint8_t byte);

#endif
