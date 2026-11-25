/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DISPLAY_VGA_PALETTE_H
#define HW_DISPLAY_VGA_PALETTE_H

#include <stdbool.h>
#include <stdint.h>

/* EGA outputs six digital color signals. VGA instead routes the attribute
 * palette value and color-select bits to an eight-bit DAC address.
 * IBM VGA Technical Reference, Attribute Mode Control and Color Select.
 */
static inline uint8_t vga_palette_index16(uint8_t attr, uint8_t mode,
                                         uint8_t page, uint8_t mask)
{
    uint8_t index = ((page & 0xc) << 4) | (attr & 0x3f);

    if (mode & 0x80) {
        index = ((page & 0xf) << 4) | (attr & 0xf);
    }
    return index & mask;
}

/* In 256-color modes the pixel supplies the DAC address directly. */
static inline uint8_t vga_palette_index256(uint8_t pixel, uint8_t mask)
{
    return pixel & mask;
}

/* Retain QEMU's existing six-bit expansion, including Cirrus users. */
static inline int c6_to_8(int v)
{
    int b;
    v &= 0x3f;
    b = v & 1;
    return (v << 2) | (b << 1) | b;
}

static inline uint8_t vga_dac_component(uint8_t value, bool dac_8bit)
{
    return dac_8bit ? value : c6_to_8(value);
}

#endif
