/* CT1741 DSP command framing and PCM block units.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_AUDIO_CT1741_DSP_H
#define HW_AUDIO_CT1741_DSP_H

/* Returns -1 for commands not handled by this unsupported-command table. */
int ct1741_unimplemented_arg_count(uint8_t cmd);
unsigned int ct1741_pcm_block_bytes(uint16_t length, bool wide);

/* Direct DAC samples are held in virtual time and resampled to this
 * fixed output rate. Queue capacity is in mono U8 frames. */
#define CT1741_DAC_RATE 44100
#define CT1741_DAC_CAPACITY 8192

typedef struct CT1741DAC {
    int64_t last_ns;
    uint32_t remainder;
    unsigned int head;
    unsigned int count;
    uint8_t sample;
    uint8_t queue[CT1741_DAC_CAPACITY];
} CT1741DAC;

void ct1741_dac_reset(CT1741DAC *dac, int64_t now, uint8_t sample);
void ct1741_dac_advance(CT1741DAC *dac, int64_t now);
void ct1741_dac_write(CT1741DAC *dac, int64_t now, uint8_t sample);
size_t ct1741_dac_peek(const CT1741DAC *dac, const uint8_t **data);
void ct1741_dac_consume(CT1741DAC *dac, size_t frames);

#endif
