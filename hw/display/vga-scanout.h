/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DISPLAY_VGA_SCANOUT_H
#define HW_DISPLAY_VGA_SCANOUT_H

#include <stdbool.h>
#include <stdint.h>

/* VGA CRTC mode-control address substitutions for CGA/EGA compatibility.
 * Addresses here are QEMU's interleaved VGA VRAM byte offsets, not CGA
 * guest-visible offsets. Native VGA addressing has both map bits set.
 */
static inline uint32_t vga_scanline_address(uint32_t addr, uint8_t mode,
                                            unsigned row)
{
    if (!(mode & 1)) {
        unsigned shift = 14 + ((mode >> 6) & 1);

        addr = (addr & ~(UINT32_C(1) << shift)) | ((row & 1) << shift);
    }
    if (!(mode & 2)) {
        addr = (addr & ~UINT32_C(0x8000)) | ((row & 2) << 14);
    }
    return addr;
}

static inline unsigned vga_scanline_repeat(uint8_t mode, uint8_t max_scan)
{
    unsigned double_scan = max_scan >> 7;

    if (mode & 1) {
        return (((max_scan & 0x1f) + 1) << double_scan) - 1;
    }
    /* Preserve the existing VGA CGA-compatibility repeat policy. */
    return double_scan;
}

static inline bool vga_scanline_advance(uint8_t mode, unsigned row)
{
    unsigned mask = (mode & 3) ^ 3;

    return (row & mask) == mask;
}

#endif
