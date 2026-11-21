/*
 * Creative Music System SAA1099 PCM mixing helpers.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_GAMEBLASTER_SAA1099_H
#define HW_AUDIO_GAMEBLASTER_SAA1099_H

#include <stdbool.h>
#include <stdint.h>

/* Signed, AC-centered PCM level in half-amplitude units (-2 to +2).
 * With both generators enabled, high noise halves the tone amplitude.
 * Do not turn the half-amplitude state into silence.
 */
static inline int cms_voice_signed_level(bool tone_enabled, bool noise_enabled,
                                         bool tone_high, bool noise_high)
{
    if (tone_enabled) {
        int polarity = tone_high ? 1 : -1;

        return polarity * (noise_enabled && noise_high ? 1 : 2);
    }
    if (noise_enabled) {
        return noise_high ? 2 : -2;
    }
    return 0;
}

/* The three-bit envelope mask applies *after* right-channel inversion.
 * Inverting an already masked four-bit value would reintroduce its LSB.
 */
static inline unsigned cms_envelope_stereo_level(uint8_t config,
                                                 unsigned level, bool right)
{
    unsigned mask = (config & 0x10) ? 0x0e : 0x0f;

    if (right && (config & 0x01)) {
        level = 15 - level;
    }
    return level & mask;
}

#endif /* HW_AUDIO_GAMEBLASTER_SAA1099_H */
