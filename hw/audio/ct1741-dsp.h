/* CT1741 DSP command framing and PCM block units.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_CT1741_DSP_H
#define HW_AUDIO_CT1741_DSP_H

/* Returns -1 for commands not handled by this unsupported-command table. */
int ct1741_unimplemented_arg_count(uint8_t cmd);
unsigned int ct1741_pcm_block_bytes(uint16_t length, bool wide);

#endif
