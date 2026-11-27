/*
 * Cirrus Logic CL-GD5446 display clock and retrace timing.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/host-utils.h"
#include "qemu/timer.h"
#include "cirrus_vga_internal.h"

#define CIRRUS_REFCLK_HZ 14318180U
#define CIRRUS_MAX_VCLK_HZ 135000000U

/*
 * GD5446 TRM sections 4.5, 8.5, 8.17 and 9.9.
 * The programmable clock uses a seven-bit numerator, five-bit
 * denominator and a divide-by-two post-scalar. The default frequencies
 * also provide a deterministic fallback while the PLL is unprogrammed.
 */
static uint32_t cirrus_gd5446_vclk(const VGACommonState *vga)
{
    static const uint32_t defaults[] = {
        25180000, 28325000, 41165000, 36082000
    };
    unsigned sel = (vga->msr >> 2) & 3;
    unsigned n = vga->sr[0x0b + sel] & 0x7f;
    unsigned d = (vga->sr[0x1b + sel] >> 1) & 0x1f;
    unsigned post = 1 + (vga->sr[0x1b + sel] & 1);
    uint64_t hz;

    if (!n || !d) {
        return defaults[sel];
    }
    hz = (uint64_t)CIRRUS_REFCLK_HZ * n / (d * post);
    return hz > CIRRUS_MAX_VCLK_HZ ? defaults[sel] : hz;
}

/* End registers contain the low bits of a counter, not a duration. */
static unsigned counter_end(unsigned start, unsigned end, unsigned mask)
{
    unsigned delta = (end - start) & mask;

    return start + (delta ? delta : mask + 1);
}

void cirrus_gd5446_update_retrace_info(VGACommonState *vga)
{
    CirrusVGAState *s = container_of(vga, CirrusVGAState, vga);
    CirrusDisplayTiming *t = &s->display_timing;
    const uint8_t *cr = vga->cr;
    unsigned dots = (vga->sr[1] & 1) ? 8 : 9;
    unsigned divider = (vga->sr[1] & 8) ? 2 : 1;

    /* TRM 8.37: double-clock indexed mode clocks the CRTC at VCLK/2. */
    if (cirrus_gd5446_double_clock_palette(s)) {
        divider *= 2;
    }
    /* TRM 4.16: SR1, not MISC[0], selects the character width. */
    t->character_hz = cirrus_gd5446_vclk(vga) / (dots * divider);
    t->htotal = cr[0] + 5;
    t->vtotal = (cr[6] | ((cr[7] & 1) << 8) |
                 ((cr[7] & 0x20) << 4)) + 2;

    t->vsync_start = cr[0x10] | ((cr[7] & 4) << 6) |
                     ((cr[7] & 0x80) << 2);
    t->vsync_end = counter_end(t->vsync_start, cr[0x11] & 15, 15);

    /* Standard VGA blanking counters. Extended CRTC modes are separate. */
    t->hblank_start = cr[2];
    t->hblank_end = counter_end(t->hblank_start,
                               (cr[3] & 31) | ((cr[5] & 0x80) >> 2), 63);
    t->vblank_start = cr[0x15] | ((cr[7] & 8) << 5) |
                      ((cr[9] & 0x20) << 4);
    t->vblank_end = counter_end(t->vblank_start, cr[0x16], 255);
}

uint8_t cirrus_gd5446_retrace(VGACommonState *vga)
{
    CirrusVGAState *s = container_of(vga, CirrusVGAState, vga);
    const CirrusDisplayTiming *t = &s->display_timing;
    uint8_t val = vga->st01 & ~(ST01_V_RETRACE | ST01_DISP_ENABLE);
    uint64_t character;
    unsigned line, column;

    if (!t->character_hz || !t->htotal || !t->vtotal) {
        return val;
    }

    /* Virtual time, no host sleeps or per-scanline timer callbacks. */
    character = muldiv64(qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL),
                         t->character_hz, NANOSECONDS_PER_SECOND);
    character %= (uint64_t)t->htotal * t->vtotal;
    line = character / t->htotal;
    column = character % t->htotal;

    if (line >= t->vsync_start && line < t->vsync_end) {
        val |= ST01_V_RETRACE;
    }
    if ((vga->sr[1] & 0x20) ||
        (line >= t->vblank_start && line < t->vblank_end) ||
        (column >= t->hblank_start && column < t->hblank_end)) {
        val |= ST01_DISP_ENABLE;
    }
    return val;
}
