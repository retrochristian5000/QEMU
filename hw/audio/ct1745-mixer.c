/*
 * Creative CT1745 mixer register state.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Creative Sound Blaster Series Hardware Programming Guide, chapter 4.
 * This models register readback, not analog signal processing.
 */
#include "qemu/osdep.h"
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
