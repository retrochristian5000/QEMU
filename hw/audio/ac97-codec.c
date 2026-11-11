/*
 * Reusable AC'97 codec register-file helpers
 *
 * Keep codec register defaults and register semantics separate from the host
 * controller.  QEMU has several AC'97/MC'97 links (Intel, VIA, SoundFusion,
 * and PL041) whose transport/DMA engines differ substantially even though
 * they talk to the same class of codec registers.
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

static const AC97CodecRegDefault lm4549_defaults[] = {
    { AC97_Reset,                     0x0d50 },
    { AC97_Master_Volume_Mute,        0x8008 },
    { AC97_Headphone_Volume_Mute,     0x8000 },
    { AC97_Master_Volume_Mono_Mute,   0x8000 },
    { AC97_PC_BEEP_Volume_Mute,       0x0000 },
    { AC97_Phone_Volume_Mute,         0x8008 },
    { AC97_Mic_Volume_Mute,           0x8008 },
    { AC97_Line_In_Volume_Mute,       0x8808 },
    { AC97_CD_Volume_Mute,             0x8808 },
    { AC97_Video_Volume_Mute,          0x8808 },
    { AC97_Aux_Volume_Mute,            0x8808 },
    { AC97_PCM_Out_Volume_Mute,        0x8808 },
    { AC97_Record_Select,              0x0000 },
    { AC97_Record_Gain_Mute,           0x8000 },
    { AC97_General_Purpose,            0x0000 },
    { AC97_3D_Control,                 0x0101 },
    { AC97_Powerdown_Ctrl_Stat,        0x000f },
    { AC97_Extended_Audio_ID,          0x0001 },
    { AC97_Extended_Audio_Ctrl_Stat,   0x0000 },
    { AC97_PCM_Front_DAC_Rate,         48000 },
    { AC97_PCM_LR_ADC_Rate,            48000 },
};

/*
 * Generic MC'97 modem personality.  Model only the standardized one-line
 * modem function here.  Concrete silicon can override the vendor ID and add
 * Line2, handset, caller-ID, or vendor-specific behavior later.
 */
static const AC97CodecRegDefault mc97_modem_defaults[] = {
    { AC97_Reset,                     0x0000 },
    { AC97_Extended_Modem_ID,         AC97_MEI_LINE1 },
    { AC97_Extended_Modem_Ctrl_Stat,  AC97_MEA_GPIO | AC97_MEA_MREF |
                                         AC97_MEA_ADC1 | AC97_MEA_DAC1 },
    { AC97_Modem_Line1_Rate,          8000 },
    { AC97_Modem_Line1_Level,         0x0000 },
    { AC97_Modem_GPIO_Config,         0x0000 },
    { AC97_Modem_GPIO_Polarity,       0x0000 },
    { AC97_Modem_GPIO_Sticky,         0x0000 },
    { AC97_Modem_GPIO_Wakeup,         0x0000 },
    { AC97_Modem_GPIO_Status,         0x0000 },
    { AC97_Modem_Misc_AFE,            0x0000 },
};

const AC97CodecProfile ac97_codec_profile_minimal = {
    .name = "minimal",
    .kind = AC97_CODEC_PROFILE_MINIMAL,
    .clear_on_reset = true,
};

const AC97CodecProfile ac97_codec_profile_stac9700 = {
    .name = "STAC9700",
    .kind = AC97_CODEC_PROFILE_STAC9700,
    .defaults = stac9700_defaults,
    .num_defaults = ARRAY_SIZE(stac9700_defaults),
    .vendor_id = 0x83847600,
    .clear_on_reset = true,
};

const AC97CodecProfile ac97_codec_profile_stac9766 = {
    .name = "STAC9766",
    .kind = AC97_CODEC_PROFILE_STAC9766,
    .defaults = stac9766_defaults,
    .num_defaults = ARRAY_SIZE(stac9766_defaults),
    .vendor_id = 0x83847666,
    .clear_on_reset = true,
};

const AC97CodecProfile ac97_codec_profile_lm4549 = {
    .name = "LM4549",
    .kind = AC97_CODEC_PROFILE_LM4549,
    .defaults = lm4549_defaults,
    .num_defaults = ARRAY_SIZE(lm4549_defaults),
    .vendor_id = 0x4e534331,
    /* Preserve the historical QEMU model's partial-reset behavior. */
    .clear_on_reset = false,
};

const AC97CodecProfile ac97_codec_profile_mc97_modem = {
    .name = "MC97 modem",
    .kind = AC97_CODEC_PROFILE_MC97_MODEM,
    .defaults = mc97_modem_defaults,
    .num_defaults = ARRAY_SIZE(mc97_modem_defaults),
    .clear_on_reset = true,
};

void ac97_codec_init_u16(AC97Codec *codec,
                         uint16_t regs[AC97_CODEC_REGS],
                         const AC97CodecProfile *profile,
                         uint32_t vendor_id_override)
{
    *codec = (AC97Codec) {
        .data = regs,
        .data_size = sizeof(uint16_t) * AC97_CODEC_REGS,
        .storage = AC97_CODEC_STORAGE_U16,
        .profile = profile,
        .vendor_id_override = vendor_id_override,
    };
}

void ac97_codec_init_u16_offsets(AC97Codec *codec,
                                 uint16_t regs[AC97_CODEC_REGS],
                                 const AC97CodecProfile *profile,
                                 uint32_t vendor_id_override)
{
    *codec = (AC97Codec) {
        .data = regs,
        .data_size = sizeof(uint16_t) * AC97_CODEC_REGS,
        .storage = AC97_CODEC_STORAGE_U16_OFFSETS,
        .profile = profile,
        .vendor_id_override = vendor_id_override,
    };
}

void ac97_codec_init_le_bytes(AC97Codec *codec, uint8_t *data,
                              size_t data_size,
                              const AC97CodecProfile *profile,
                              uint32_t vendor_id_override)
{
    *codec = (AC97Codec) {
        .data = data,
        .data_size = data_size,
        .storage = AC97_CODEC_STORAGE_LE_BYTES,
        .profile = profile,
        .vendor_id_override = vendor_id_override,
    };
}

static bool ac97_codec_reg_valid(const AC97Codec *codec, unsigned reg)
{
    switch (codec->storage) {
    case AC97_CODEC_STORAGE_U16:
        return !(reg & 1) && (reg >> 1) < codec->data_size / sizeof(uint16_t);
    case AC97_CODEC_STORAGE_U16_OFFSETS:
        return reg < codec->data_size / sizeof(uint16_t);
    case AC97_CODEC_STORAGE_LE_BYTES:
        return !(reg & 1) && reg + 2 <= codec->data_size;
    default:
        return false;
    }
}

uint16_t ac97_codec_read(const AC97Codec *codec, unsigned reg)
{
    const uint16_t *regs;
    const uint8_t *data;

    if (!ac97_codec_reg_valid(codec, reg)) {
        return 0xffff;
    }

    switch (codec->storage) {
    case AC97_CODEC_STORAGE_U16:
        regs = codec->data;
        return regs[reg >> 1];
    case AC97_CODEC_STORAGE_U16_OFFSETS:
        regs = codec->data;
        return regs[reg];
    case AC97_CODEC_STORAGE_LE_BYTES:
        data = codec->data;
        return data[reg] | (data[reg + 1] << 8);
    default:
        return 0xffff;
    }
}

void ac97_codec_write_raw(AC97Codec *codec, unsigned reg, uint16_t value)
{
    uint16_t *regs;
    uint8_t *data;

    if (!ac97_codec_reg_valid(codec, reg)) {
        return;
    }

    switch (codec->storage) {
    case AC97_CODEC_STORAGE_U16:
        regs = codec->data;
        regs[reg >> 1] = value;
        break;
    case AC97_CODEC_STORAGE_U16_OFFSETS:
        regs = codec->data;
        regs[reg] = value;
        break;
    case AC97_CODEC_STORAGE_LE_BYTES:
        data = codec->data;
        data[reg] = value & 0xff;
        data[reg + 1] = value >> 8;
        break;
    }
}

void ac97_codec_reset(AC97Codec *codec)
{
    const AC97CodecProfile *profile = codec->profile;
    uint32_t vendor_id = codec->vendor_id_override;
    size_t i;

    if (!profile || profile->clear_on_reset) {
        memset(codec->data, 0, codec->data_size);
    }

    if (profile) {
        for (i = 0; i < profile->num_defaults; i++) {
            const AC97CodecRegDefault *d = &profile->defaults[i];
            ac97_codec_write_raw(codec, d->reg, d->value);
        }
        if (!vendor_id) {
            vendor_id = profile->vendor_id;
        }
    }

    if (vendor_id) {
        ac97_codec_write_raw(codec, AC97_Vendor_ID1, vendor_id >> 16);
        ac97_codec_write_raw(codec, AC97_Vendor_ID2, vendor_id & 0xffff);
    }
}

static uint16_t ac97_stac9766_rate(uint16_t value)
{
    static const uint16_t rates[] = {
        8000, 11025, 16000, 22050, 32000, 44100, 48000,
    };
    size_t i;

    for (i = 0; i < ARRAY_SIZE(rates) - 1; i++) {
        if (value < rates[i] + (rates[i + 1] - rates[i]) / 2) {
            return rates[i];
        }
    }
    return 48000;
}

static uint32_t ac97_codec_write_stac9766(AC97Codec *codec,
                                           unsigned reg, uint16_t value)
{
    switch (reg) {
    case AC97_Reset:
        ac97_codec_reset(codec);
        return 0;

    case AC97_Master_Volume_Mute:
        if (value & (1u << 13)) {
            value |= 0x1f00;
        }
        if (value & (1u << 5)) {
            value |= 0x001f;
        }
        ac97_codec_write_raw(codec, reg, value & 0x9f1f);
        return AC97_CODEC_EVENT_VOLUME_OUT;

    case AC97_PCM_Out_Volume_Mute:
        ac97_codec_write_raw(codec, reg, value & 0x9f1f);
        return AC97_CODEC_EVENT_VOLUME_OUT;

    case AC97_Extended_Audio_Ctrl_Stat: {
        uint16_t old = ac97_codec_read(codec, reg);
        uint32_t events = 0;

        old &= ~EACS_VRA;
        old |= value & EACS_VRA;
        ac97_codec_write_raw(codec, reg, old);
        if (!(value & EACS_VRA)) {
            ac97_codec_write_raw(codec, AC97_PCM_Front_DAC_Rate, 48000);
            ac97_codec_write_raw(codec, AC97_PCM_LR_ADC_Rate, 48000);
            events |= AC97_CODEC_EVENT_FRONT_DAC_RATE |
                      AC97_CODEC_EVENT_LR_ADC_RATE;
        }
        return events;
    }

    case AC97_PCM_Front_DAC_Rate:
        if (ac97_codec_read(codec, AC97_Extended_Audio_Ctrl_Stat) & EACS_VRA) {
            ac97_codec_write_raw(codec, reg, ac97_stac9766_rate(value));
            return AC97_CODEC_EVENT_FRONT_DAC_RATE;
        }
        return 0;

    case AC97_PCM_LR_ADC_Rate:
        if (ac97_codec_read(codec, AC97_Extended_Audio_Ctrl_Stat) & EACS_VRA) {
            ac97_codec_write_raw(codec, reg, ac97_stac9766_rate(value));
            return AC97_CODEC_EVENT_LR_ADC_RATE;
        }
        return 0;

    case AC97_Powerdown_Ctrl_Stat:
        value = (value & 0xff00) | (ac97_codec_read(codec, reg) & 0x00ff);
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Extended_Audio_ID:
    case AC97_Vendor_ID1:
    case AC97_Vendor_ID2:
        return 0;

    default:
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }
}

static uint32_t ac97_codec_write_stac9700(AC97Codec *codec,
                                           unsigned reg, uint16_t value)
{
    switch (reg) {
    case AC97_Reset:
        ac97_codec_reset(codec);
        return 0;

    case AC97_Powerdown_Ctrl_Stat:
        value &= ~0x800f;
        value |= ac97_codec_read(codec, reg) & 0x000f;
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Master_Volume_Mute:
        ac97_codec_write_raw(codec, reg, value & 0xbf3f);
        return AC97_CODEC_EVENT_VOLUME_OUT;

    case AC97_PCM_Out_Volume_Mute:
        ac97_codec_write_raw(codec, reg, value & 0x9f1f);
        return AC97_CODEC_EVENT_VOLUME_OUT;

    case AC97_Record_Gain_Mute:
        ac97_codec_write_raw(codec, reg, value & 0x8f0f);
        return AC97_CODEC_EVENT_VOLUME_IN;

    case AC97_Record_Select: {
        uint8_t right = value & 7;
        uint8_t left = (value >> 8) & 7;
        ac97_codec_write_raw(codec, reg, right | (left << 8));
        return 0;
    }

    case AC97_Vendor_ID1:
    case AC97_Vendor_ID2:
    case AC97_Extended_Audio_ID:
        return 0;

    case AC97_Extended_Audio_Ctrl_Stat: {
        uint32_t events = 0;

        if (!(value & EACS_VRA)) {
            ac97_codec_write_raw(codec, AC97_PCM_Front_DAC_Rate, 48000);
            ac97_codec_write_raw(codec, AC97_PCM_LR_ADC_Rate, 48000);
            events |= AC97_CODEC_EVENT_FRONT_DAC_RATE |
                      AC97_CODEC_EVENT_LR_ADC_RATE;
        }
        if (!(value & EACS_VRM)) {
            ac97_codec_write_raw(codec, AC97_MIC_ADC_Rate, 48000);
            events |= AC97_CODEC_EVENT_MIC_ADC_RATE;
        }
        ac97_codec_write_raw(codec, reg, value);
        return events;
    }

    case AC97_PCM_Front_DAC_Rate:
        if (ac97_codec_read(codec, AC97_Extended_Audio_Ctrl_Stat) & EACS_VRA) {
            ac97_codec_write_raw(codec, reg, value);
            return AC97_CODEC_EVENT_FRONT_DAC_RATE;
        }
        return 0;

    case AC97_MIC_ADC_Rate:
        if (ac97_codec_read(codec, AC97_Extended_Audio_Ctrl_Stat) & EACS_VRM) {
            ac97_codec_write_raw(codec, reg, value);
            return AC97_CODEC_EVENT_MIC_ADC_RATE;
        }
        return 0;

    case AC97_PCM_LR_ADC_Rate:
        if (ac97_codec_read(codec, AC97_Extended_Audio_Ctrl_Stat) & EACS_VRA) {
            ac97_codec_write_raw(codec, reg, value);
            return AC97_CODEC_EVENT_LR_ADC_RATE;
        }
        return 0;

    case AC97_Headphone_Volume_Mute:
    case AC97_Master_Volume_Mono_Mute:
    case AC97_Master_Tone_RL:
    case AC97_PC_BEEP_Volume_Mute:
    case AC97_Phone_Volume_Mute:
    case AC97_Mic_Volume_Mute:
    case AC97_Line_In_Volume_Mute:
    case AC97_CD_Volume_Mute:
    case AC97_Video_Volume_Mute:
    case AC97_Aux_Volume_Mute:
    case AC97_Record_Gain_Mic_Mute:
    case AC97_General_Purpose:
    case AC97_3D_Control:
    case AC97_Sigmatel_Analog:
    case AC97_Sigmatel_Dac2Invert:
        return 0;

    default:
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }
}

static uint32_t ac97_codec_write_lm4549(AC97Codec *codec,
                                         unsigned reg, uint16_t value)
{
    switch (reg) {
    case AC97_Reset:
        ac97_codec_reset(codec);
        return 0;

    case AC97_PCM_Front_DAC_Rate:
        if (value < 4000 || value > 48000) {
            return AC97_CODEC_EVENT_INVALID_RATE;
        }
        ac97_codec_write_raw(codec, reg, value);
        return AC97_CODEC_EVENT_FRONT_DAC_RATE;

    case AC97_Powerdown_Ctrl_Stat:
        value &= ~0x000f;
        value |= ac97_codec_read(codec, reg) & 0x000f;
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Extended_Audio_ID:
    case AC97_Vendor_ID1:
    case AC97_Vendor_ID2:
        return 0;

    default:
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }
}

static uint16_t ac97_mc97_ready_bits(uint16_t ext_mid, uint16_t power)
{
    uint16_t ready = AC97_MEA_MREF;

    if (!(power & AC97_MEA_PRA)) {
        ready |= AC97_MEA_GPIO;
    }
    if (ext_mid & AC97_MEI_LINE1) {
        if (!(power & AC97_MEA_PRC)) {
            ready |= AC97_MEA_ADC1;
        }
        if (!(power & AC97_MEA_PRD)) {
            ready |= AC97_MEA_DAC1;
        }
    }
    if (ext_mid & AC97_MEI_LINE2) {
        if (!(power & AC97_MEA_PRE)) {
            ready |= AC97_MEA_ADC2;
        }
        if (!(power & AC97_MEA_PRF)) {
            ready |= AC97_MEA_DAC2;
        }
    }
    if (ext_mid & AC97_MEI_HANDSET) {
        if (!(power & AC97_MEA_PRG)) {
            ready |= AC97_MEA_HADC;
        }
        if (!(power & AC97_MEA_PRH)) {
            ready |= AC97_MEA_HDAC;
        }
    }
    return ready;
}

static uint32_t ac97_codec_write_mc97(AC97Codec *codec,
                                       unsigned reg, uint16_t value)
{
    uint16_t ext_mid = ac97_codec_read(codec, AC97_Extended_Modem_ID);

    switch (reg) {
    case AC97_Reset:
        ac97_codec_reset(codec);
        return 0;

    case AC97_Extended_Modem_ID:
    case AC97_Vendor_ID1:
    case AC97_Vendor_ID2:
        return 0;

    case AC97_Extended_Modem_Ctrl_Stat: {
        uint16_t power = value & AC97_MEA_POWER_MASK;
        uint16_t ready = ac97_mc97_ready_bits(ext_mid, power);

        ac97_codec_write_raw(codec, reg, power | ready);
        return 0;
    }

    case AC97_Modem_Line1_Rate:
        if (!(ext_mid & AC97_MEI_LINE1)) {
            return 0;
        }
        if (value < 8000 || value > 16000) {
            return AC97_CODEC_EVENT_INVALID_RATE;
        }
        ac97_codec_write_raw(codec, reg, value);
        return AC97_CODEC_EVENT_MODEM_LINE1_RATE;

    case AC97_Modem_Line2_Rate:
        if (!(ext_mid & AC97_MEI_LINE2)) {
            return 0;
        }
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Modem_Handset_Rate:
        if (!(ext_mid & AC97_MEI_HANDSET)) {
            return 0;
        }
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Modem_Line1_Level:
        if (!(ext_mid & AC97_MEI_LINE1)) {
            return 0;
        }
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Modem_Line2_Level:
        if (!(ext_mid & AC97_MEI_LINE2)) {
            return 0;
        }
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Modem_Handset_Level:
        if (!(ext_mid & AC97_MEI_HANDSET)) {
            return 0;
        }
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    case AC97_Modem_GPIO_Config:
    case AC97_Modem_GPIO_Polarity:
    case AC97_Modem_GPIO_Sticky:
    case AC97_Modem_GPIO_Wakeup:
    case AC97_Modem_GPIO_Status:
        ac97_codec_write_raw(codec, reg, value);
        return AC97_CODEC_EVENT_MODEM_GPIO;

    case AC97_Modem_Misc_AFE:
        ac97_codec_write_raw(codec, reg, value);
        return 0;

    default:
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }
}

uint32_t ac97_codec_write(AC97Codec *codec, unsigned reg, uint16_t value)
{
    if (!ac97_codec_reg_valid(codec, reg)) {
        return 0;
    }

    if (!codec->profile) {
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }

    switch (codec->profile->kind) {
    case AC97_CODEC_PROFILE_STAC9700:
        return ac97_codec_write_stac9700(codec, reg, value);
    case AC97_CODEC_PROFILE_STAC9766:
        return ac97_codec_write_stac9766(codec, reg, value);
    case AC97_CODEC_PROFILE_LM4549:
        return ac97_codec_write_lm4549(codec, reg, value);
    case AC97_CODEC_PROFILE_MC97_MODEM:
        return ac97_codec_write_mc97(codec, reg, value);
    case AC97_CODEC_PROFILE_MINIMAL:
    default:
        ac97_codec_write_raw(codec, reg, value);
        return 0;
    }
}
