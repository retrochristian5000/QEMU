/*
 * Reusable AC'97 codec register-file helpers
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_AC97_CODEC_H
#define HW_AUDIO_AC97_CODEC_H

#include "qemu/osdep.h"

#define AC97_CODEC_REGS 128

typedef struct AC97CodecRegDefault {
    uint8_t reg;
    uint16_t value;
} AC97CodecRegDefault;

typedef struct AC97CodecProfile {
    const char *name;
    const AC97CodecRegDefault *defaults;
    size_t num_defaults;
    uint32_t vendor_id;
} AC97CodecProfile;

/*
 * The minimal profile intentionally supplies no functional defaults.  It is
 * useful for controllers whose companion codec has not yet been identified;
 * a caller can still provide a vendor-id override without inventing the rest
 * of the codec personality.
 */
extern const AC97CodecProfile ac97_codec_profile_minimal;
extern const AC97CodecProfile ac97_codec_profile_stac9700;
extern const AC97CodecProfile ac97_codec_profile_stac9766;

void ac97_codec_reset(uint16_t regs[AC97_CODEC_REGS],
                      const AC97CodecProfile *profile,
                      uint32_t vendor_id_override);
uint16_t ac97_codec_read(const uint16_t regs[AC97_CODEC_REGS], uint8_t reg);
void ac97_codec_write_raw(uint16_t regs[AC97_CODEC_REGS], uint8_t reg,
                          uint16_t value);

#endif /* HW_AUDIO_AC97_CODEC_H */
