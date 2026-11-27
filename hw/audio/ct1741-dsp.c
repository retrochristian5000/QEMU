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
