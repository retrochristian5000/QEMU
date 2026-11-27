/* Creative CT1745 mixer register interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_CT1745_MIXER_H
#define HW_AUDIO_CT1745_MIXER_H

void ct1745_reset(uint8_t regs[256]);
bool ct1745_write(uint8_t regs[256], uint8_t reg, uint8_t value);

/* Caller supplies frames * (wide ? 2 : 1) * (stereo ? 2 : 1)
 * source bytes and frames * 4 output bytes. Output is signed LE stereo. */
size_t ct1745_pcm_render(const uint8_t regs[256], const uint8_t *src,
                         size_t frames, bool wide, bool is_signed,
                         bool stereo, uint8_t *dst);

#endif
