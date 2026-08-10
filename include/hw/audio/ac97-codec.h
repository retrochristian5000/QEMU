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

typedef enum AC97CodecProfileKind {
    AC97_CODEC_PROFILE_MINIMAL,
    AC97_CODEC_PROFILE_STAC9700,
    AC97_CODEC_PROFILE_STAC9766,
    AC97_CODEC_PROFILE_LM4549,
    AC97_CODEC_PROFILE_MC97_MODEM,
} AC97CodecProfileKind;

typedef struct AC97CodecProfile {
    const char *name;
    AC97CodecProfileKind kind;
    const AC97CodecRegDefault *defaults;
    size_t num_defaults;
    uint32_t vendor_id;
    bool clear_on_reset;
} AC97CodecProfile;

typedef enum AC97CodecStorage {
    /* Packed words: AC'97 register 0x02 is regs[1]. */
    AC97_CODEC_STORAGE_U16,
    /* Historical sparse words: AC'97 register 0x02 is regs[2]. */
    AC97_CODEC_STORAGE_U16_OFFSETS,
    /* Historical byte image: register 0x02 occupies data[2..3]. */
    AC97_CODEC_STORAGE_LE_BYTES,
} AC97CodecStorage;

typedef struct AC97Codec {
    void *data;
    size_t data_size;
    AC97CodecStorage storage;
    const AC97CodecProfile *profile;
    uint32_t vendor_id_override;
} AC97Codec;

enum {
    AC97_CODEC_EVENT_VOLUME_OUT       = 1u << 0,
    AC97_CODEC_EVENT_VOLUME_IN        = 1u << 1,
    AC97_CODEC_EVENT_FRONT_DAC_RATE   = 1u << 2,
    AC97_CODEC_EVENT_LR_ADC_RATE      = 1u << 3,
    AC97_CODEC_EVENT_MIC_ADC_RATE     = 1u << 4,
    AC97_CODEC_EVENT_INVALID_RATE     = 1u << 5,
    AC97_CODEC_EVENT_MODEM_LINE1_RATE = 1u << 6,
    AC97_CODEC_EVENT_MODEM_GPIO       = 1u << 7,
};

/*
 * The minimal profile intentionally supplies no functional defaults.  It is
 * useful for controllers whose companion codec has not yet been identified;
 * a caller can still provide a vendor-id override without inventing the rest
 * of the codec personality.
 */
extern const AC97CodecProfile ac97_codec_profile_minimal;
extern const AC97CodecProfile ac97_codec_profile_stac9700;
extern const AC97CodecProfile ac97_codec_profile_stac9766;
extern const AC97CodecProfile ac97_codec_profile_lm4549;

/*
 * Generic one-line MC'97 personality.  It models only the standardized modem
 * register block and intentionally has no vendor ID; a concrete modem codec
 * should supply a vendor-id override or a more specific derived profile.
 */
extern const AC97CodecProfile ac97_codec_profile_mc97_modem;

void ac97_codec_init_u16(AC97Codec *codec,
                         uint16_t regs[AC97_CODEC_REGS],
                         const AC97CodecProfile *profile,
                         uint32_t vendor_id_override);
void ac97_codec_init_u16_offsets(AC97Codec *codec,
                                 uint16_t regs[AC97_CODEC_REGS],
                                 const AC97CodecProfile *profile,
                                 uint32_t vendor_id_override);
void ac97_codec_init_le_bytes(AC97Codec *codec, uint8_t *data,
                              size_t data_size,
                              const AC97CodecProfile *profile,
                              uint32_t vendor_id_override);
void ac97_codec_reset(AC97Codec *codec);
uint16_t ac97_codec_read(const AC97Codec *codec, unsigned reg);
void ac97_codec_write_raw(AC97Codec *codec, unsigned reg, uint16_t value);
uint32_t ac97_codec_write(AC97Codec *codec, unsigned reg, uint16_t value);

#endif /* HW_AUDIO_AC97_CODEC_H */
