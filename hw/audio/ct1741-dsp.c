/*
 * Creative CT1741 DSP 4.xx command interface.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Creative Sound Blaster Series Hardware Programming Guide, chapter 6.
 * Framing an unsupported command is not implementation of its operation.
 */
#include "qemu/osdep.h"
#include "ct1741-dsp.h"

int ct1741_unimplemented_arg_count(uint8_t cmd)
{
    switch (cmd) {
    case 0x16: /* Single-cycle 2-bit ADPCM */
    case 0x17: /* With reference byte */
    case 0x24: /* Single-cycle 8-bit ADC */
        return 2;
    case 0x38: /* DSP MIDI output */
        return 1;
    case 0x1f: /* Auto-init 2-bit ADPCM */
    case 0x2c: /* Auto-init 8-bit ADC */
    case 0x30: /* MIDI input */
    case 0x31:
    case 0x34: /* DSP UART MIDI modes */
    case 0x35:
    case 0x36:
    case 0x37:
        return 0;
    default:
        return -1;
    }
}

unsigned int ct1741_pcm_block_bytes(uint16_t length, bool wide)
{
    /* Length counts individual samples, not stereo frames. */
    return ((unsigned int)length + 1) * (wide ? 2 : 1);
}


void ct1741_dac_reset(CT1741DAC *dac, int64_t now, uint8_t sample)
{
    dac->last_ns = now;
    dac->remainder = 0;
    dac->head = 0;
    dac->count = 0;
    dac->sample = sample;
}

void ct1741_dac_advance(CT1741DAC *dac, int64_t now)
{
    uint64_t elapsed, fraction;
    unsigned int frames, tail, first, drop;

    if (now <= dac->last_ns) {
        return;
    }
    elapsed = (uint64_t)now - (uint64_t)dac->last_ns;
    dac->last_ns = now;
    fraction = (elapsed % 1000000000) * CT1741_DAC_RATE + dac->remainder;
    dac->remainder = fraction % 1000000000;
    /* One second already exceeds capacity. Avoid multiplying unbounded
     * virtual time and retain only the newest bounded interval. */
    frames = elapsed >= 1000000000 ? CT1741_DAC_CAPACITY :
             MIN(fraction / 1000000000, CT1741_DAC_CAPACITY);
    drop = MAX(0, (int)(dac->count + frames) - CT1741_DAC_CAPACITY);
    dac->head = (dac->head + drop) % CT1741_DAC_CAPACITY;
    dac->count -= drop;
    tail = (dac->head + dac->count) % CT1741_DAC_CAPACITY;
    first = MIN(frames, CT1741_DAC_CAPACITY - tail);
    memset(dac->queue + tail, dac->sample, first);
    memset(dac->queue, dac->sample, frames - first);
    dac->count += frames;
}

void ct1741_dac_write(CT1741DAC *dac, int64_t now, uint8_t sample)
{
    ct1741_dac_advance(dac, now);
    dac->sample = sample;
}

size_t ct1741_dac_peek(const CT1741DAC *dac, const uint8_t **data)
{
    *data = dac->queue + dac->head;
    return MIN(dac->count, CT1741_DAC_CAPACITY - dac->head);
}

void ct1741_dac_consume(CT1741DAC *dac, size_t frames)
{
    frames = MIN(frames, dac->count);
    dac->head = (dac->head + frames) % CT1741_DAC_CAPACITY;
    dac->count -= frames;
}
