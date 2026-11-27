/* Creative CT1745 mixer register interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_CT1745_MIXER_H
#define HW_AUDIO_CT1745_MIXER_H

void ct1745_reset(uint8_t regs[256]);
bool ct1745_write(uint8_t regs[256], uint8_t reg, uint8_t value);

#endif
