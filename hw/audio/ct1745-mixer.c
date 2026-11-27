/*
 * Creative CT1745 mixer register state.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Creative Sound Blaster Series Hardware Programming Guide, chapter 4.
 * Register state and digital approximation of the PCM output mixer.
 */
#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "ct1745-mixer.h"

typedef struct CT1745VolumePair {
    uint8_t compat;
    uint8_t left;
} CT1745VolumePair;

static const CT1745VolumePair volume_pairs[] = {
    { 0x22, 0x30 }, /* Master */
    { 0x04, 0x32 }, /* Voice */
    { 0x26, 0x34 }, /* MIDI */
    { 0x28, 0x36 }, /* CD */
    { 0x2e, 0x38 }, /* Line */
};

static void ct1745_sync_pair(uint8_t regs[256],
                             const CT1745VolumePair *pair)
{
    unsigned int left = pair->left;

    regs[pair->compat] = (regs[left] & 0xf0) | (regs[left + 1] >> 4);
}

void ct1745_reset(uint8_t regs[256])
{
    /* Reset only mixer controls; leave ISA resources and IRQ state intact. */
    memset(regs + 0x30, 0, 0x18);
    memset(regs + 0x30, 0xc0, 6); /* 24 of 31: master, voice, MIDI */
    regs[0x3c] = 0x1f;
    regs[0x3d] = 0x15;
    regs[0x3e] = 0x0b;
    memset(regs + 0x44, 0x80, 4); /* Neutral treble and bass */
    regs[0x0a] = 0;
    for (size_t i = 0; i < ARRAY_SIZE(volume_pairs); i++) {
        ct1745_sync_pair(regs, &volume_pairs[i]);
    }
}

bool ct1745_write(uint8_t regs[256], uint8_t reg, uint8_t value)
{
    for (size_t i = 0; i < ARRAY_SIZE(volume_pairs); i++) {
        const CT1745VolumePair *pair = &volume_pairs[i];
        unsigned int left = pair->left;

        if (reg == pair->compat) {
            /*
             * Map the four-bit controls to the upper four bits of the
             * five-bit controls, clearing the extra precision bit.
             */
            regs[left] = value & 0xf0;
            regs[left + 1] = (value & 0x0f) << 4;
        } else if (reg == left || reg == left + 1) {
            regs[reg] = value & 0xf8;
        } else {
            continue;
        }
        ct1745_sync_pair(regs, pair);
        return true;
    }

    switch (reg) {
    case 0x0a:
        regs[0x0a] = value & 7;
        regs[0x3a] = (value & 7) << 5;
        return true;
    case 0x3a:
        regs[0x3a] = value & 0xf8;
        regs[0x0a] = value >> 5;
        return true;
    case 0x3b:
    case 0x3f ... 0x42:
        regs[reg] = value & 0xc0;
        return true;
    case 0x3c:
        regs[reg] = value & 0x1f;
        return true;
    case 0x3d:
    case 0x3e:
        regs[reg] = value & 0x7f;
        return true;
    case 0x43:
        regs[reg] = value & 1;
        return true;
    case 0x44 ... 0x47:
        regs[reg] = value & 0xf0;
        return true;
    default:
        return false;
    }
}


/* Q24 amplitude multipliers for -124 to +18 dB, in 2 dB steps.
 * The two attenuators are cascaded before the output gain stage.
 * Integer coefficients keep results independent of the host FP library. */
static const uint32_t pcm_gain[] = {
    11, 13, 17, 21, 27, 33,
    42, 53, 67, 84, 106, 133,
    168, 211, 266, 335, 421, 531,
    668, 841, 1059, 1333, 1678, 2112,
    2659, 3347, 4214, 5305, 6679, 8409,
    10586, 13327, 16777, 21121, 26590, 33475,
    42142, 53054, 66791, 84085, 105857, 133266,
    167772, 211213, 265901, 334749, 421425, 530542,
    667913, 840853, 1058571, 1332662, 1677722, 2112126,
    2659010, 3347495, 4214246, 5305422, 6679130, 8408526,
    10585708, 13326616, 16777216, 21121264, 26590095, 33474947,
    42142461, 53054215, 66791300, 84085265, 105857077, 133266164,
};

static uint32_t ct1745_pcm_gain(const uint8_t regs[256], unsigned int channel)
{
    unsigned int level = (regs[0x30 + channel] >> 3) +
                         (regs[0x32 + channel] >> 3) +
                         3 * (regs[0x41 + channel] >> 6);

    return pcm_gain[level];
}

static int32_t pcm_decode(const uint8_t *src, bool wide, bool is_signed)
{
    if (wide) {
        uint32_t v = lduw_le_p(src);

        if (is_signed) {
            v ^= 0x8000;
        }
        return (int32_t)v - 32768;
    }

    return ((int32_t)(is_signed ? (*src ^ 0x80) : *src) - 128) * 256;
}

static int16_t pcm_scale(int32_t sample, uint32_t gain)
{
    int64_t scaled = (int64_t)sample * gain / (1 << 24);

    return CLAMP(scaled, -32768, 32767);
}

size_t ct1745_pcm_render(const uint8_t regs[256], const uint8_t *src,
                         size_t frames, bool wide, bool is_signed,
                         bool stereo, uint8_t *dst)
{
    size_t width = wide ? 2 : 1;
    uint32_t left = ct1745_pcm_gain(regs, 0);
    uint32_t right = ct1745_pcm_gain(regs, 1);

    for (size_t i = 0; i < frames; i++) {
        int32_t l = pcm_decode(src, wide, is_signed);
        int32_t r = stereo ? pcm_decode(src + width, wide, is_signed) : l;

        stw_le_p(dst, (uint16_t)pcm_scale(l, left));
        stw_le_p(dst + 2, (uint16_t)pcm_scale(r, right));
        src += width * (stereo ? 2 : 1);
        dst += 4;
    }

    return frames * 4;
}
