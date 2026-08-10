/*
 * Reusable AC'97 codec register-file helpers
 *
 * Keep codec register defaults separate from the host controller.  QEMU has
 * several AC'97 links (Intel, VIA, and now SoundFusion) whose transport/DMA
 * engines differ substantially even though they talk to the same class of
 * mixer/codec registers.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "hw/audio/ac97-codec.h"
#include "ac97.h"

static const AC97CodecRegDefault stac9700_defaults[] = {
    { AC97_Master_Volume_Mute,        0x8000 },
    { AC97_PCM_Out_Volume_Mute,       0x8808 },
    { AC97_Record_Gain_Mute,          0x8808 },
    { AC97_Powerdown_Ctrl_Stat,       0x000f },
    { AC97_Extended_Audio_ID,         0x0809 },
    { AC97_Extended_Audio_Ctrl_Stat,  0x0009 },
    { AC97_PCM_Front_DAC_Rate,        48000 },
    { AC97_PCM_Surround_DAC_Rate,     48000 },
    { AC97_PCM_LFE_DAC_Rate,          48000 },
    { AC97_PCM_LR_ADC_Rate,           48000 },
    { AC97_MIC_ADC_Rate,              48000 },
};

static const AC97CodecRegDefault stac9766_defaults[] = {
    { AC97_Reset,                     0x6a90 },
    { AC97_Master_Volume_Mute,        0x8000 },
    { AC97_Headphone_Volume_Mute,     0x8000 },
    { AC97_Master_Volume_Mono_Mute,   0x8000 },
    { AC97_Phone_Volume_Mute,         0x8008 },
    { AC97_Mic_Volume_Mute,           0x8008 },
    { AC97_Line_In_Volume_Mute,       0x8808 },
    { AC97_CD_Volume_Mute,            0x8808 },
    { AC97_Video_Volume_Mute,         0x8808 },
    { AC97_Aux_Volume_Mute,           0x8808 },
    { AC97_PCM_Out_Volume_Mute,       0x8808 },
    { AC97_Record_Gain_Mute,          0x8000 },
    { AC97_Powerdown_Ctrl_Stat,       0x000f },
    { AC97_Extended_Audio_ID,         0x0a05 },
    { AC97_Extended_Audio_Ctrl_Stat,  0x0400 },
    { AC97_PCM_Front_DAC_Rate,        48000 },
    { AC97_PCM_LR_ADC_Rate,           48000 },
};

const AC97CodecProfile ac97_codec_profile_minimal = {
    .name = "minimal",
};

const AC97CodecProfile ac97_codec_profile_stac9700 = {
    .name = "STAC9700",
    .defaults = stac9700_defaults,
    .num_defaults = ARRAY_SIZE(stac9700_defaults),
    .vendor_id = 0x83847600,
};

const AC97CodecProfile ac97_codec_profile_stac9766 = {
    .name = "STAC9766",
    .defaults = stac9766_defaults,
    .num_defaults = ARRAY_SIZE(stac9766_defaults),
    .vendor_id = 0x83847666,
};

void ac97_codec_reset(uint16_t regs[AC97_CODEC_REGS],
                      const AC97CodecProfile *profile,
                      uint32_t vendor_id_override)
{
    uint32_t vendor_id;
    size_t i;

    memset(regs, 0, sizeof(uint16_t) * AC97_CODEC_REGS);

    if (profile) {
        for (i = 0; i < profile->num_defaults; i++) {
            const AC97CodecRegDefault *d = &profile->defaults[i];

            if (!(d->reg & 1)) {
                regs[d->reg >> 1] = d->value;
            }
        }
    }

    vendor_id = vendor_id_override;
    if (!vendor_id && profile) {
        vendor_id = profile->vendor_id;
    }

    if (vendor_id) {
        regs[AC97_Vendor_ID1 >> 1] = vendor_id >> 16;
        regs[AC97_Vendor_ID2 >> 1] = vendor_id & 0xffff;
    }
}

uint16_t ac97_codec_read(const uint16_t regs[AC97_CODEC_REGS], unsigned reg)
{
    if ((reg & 1) || reg >= AC97_CODEC_REGS * 2) {
        return 0xffff;
    }

    return regs[reg >> 1];
}

void ac97_codec_write_raw(uint16_t regs[AC97_CODEC_REGS], unsigned reg,
                          uint16_t value)
{
    if ((reg & 1) || reg >= AC97_CODEC_REGS * 2) {
        return;
    }

    regs[reg >> 1] = value;
}
