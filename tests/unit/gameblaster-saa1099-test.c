/*
 * Hardware-regression checks for the SAA1099 digital mixing path.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

#include "gameblaster-saa1099.h"

static void test_voice_mixer(void)
{
    for (int tone = 0; tone <= 1; tone++) {
        for (int noise = 0; noise <= 1; noise++) {
            for (int tone_high = 0; tone_high <= 1; tone_high++) {
                for (int noise_high = 0; noise_high <= 1; noise_high++) {
                    int level = cms_voice_signed_level(tone, noise,
                                        tone_high, noise_high);
                    int expected;

                    if (tone) {
                        expected = (tone_high ? 1 : -1) *
                                   (noise && noise_high ? 1 : 2);
                    } else if (noise) {
                        expected = noise_high ? 2 : -2;
                    } else {
                        expected = 0;
                    }
                    assert(level == expected);
                }
            }
        }
    }
    /* A high tone remains audible for either noise bit value. */
    assert(cms_voice_signed_level(true, true, true, false) == 2);
    assert(cms_voice_signed_level(true, true, true, true) == 1);
    assert(cms_voice_signed_level(true, true, false, true) == -1);
}

static void test_envelope_resolution(void)
{
    for (unsigned level = 0; level <= 15; level++) {
        for (unsigned flags = 0; flags < 4; flags++) {
            uint8_t config = ((flags & 2) ? 0x10 : 0) |
                             ((flags & 1) ? 0x01 : 0);
            unsigned mask = (flags & 2) ? 0x0e : 0x0f;
            unsigned left = cms_envelope_stereo_level(config, level, false);
            unsigned right = cms_envelope_stereo_level(config, level, true);

            assert(left == (level & mask));
            assert(right == (((flags & 1) ? 15 - level : level) & mask));
            if (flags & 2) {
                assert((left & 1) == 0);
                assert((right & 1) == 0);
            }
        }
    }
    assert(cms_envelope_stereo_level(0x11, 0, true) == 14);
    assert(cms_envelope_stereo_level(0x01, 0, true) == 15);
}

int main(void)
{
    test_voice_mixer();
    test_envelope_resolution();
    return 0;
}
