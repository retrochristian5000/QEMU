/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "hw/display/cirrus_vga_overlay.h"

int main(void)
{
    uint8_t cr[256] = { 0 };
    uint8_t vram[128] = { 0 };
    uint32_t dst[8];
    CirrusOverlay w;

    assert(cirrus_overlay_reg_mask(0x36) == 0x3f);
    assert(cirrus_overlay_reg_mask(0x3c) == 0x2f);
    assert(cirrus_overlay_reg_mask(0x3e) == 0xbf);
    assert(cirrus_overlay_reg_mask(0x3f) == 0x33);
    assert(cirrus_overlay_reg_mask(0x5e) == 0x37);
    assert(!cirrus_overlay_decode(cr, 16, &w));

    /* Start x=3, width=4, rows 2..3; source address=18, pitch=8. */
    cr[0x33] = 1;
    cr[0x34] = 2;
    cr[0x35] = 2;
    cr[0x37] = 2;
    cr[0x38] = 3;
    cr[0x3a] = 4;
    cr[0x3d] = 1;
    cr[0x3e] = 0x0b;
    cr[0x5d] = 0x0a;
    assert(cirrus_overlay_decode(cr, 16, &w));
    assert(w.x == 3 && w.width == 4 && w.top == 2 && w.bottom == 3);
    assert(w.base == 18 && w.pitch == 8 && w.source_bytes == 8);

    vram[19] = 0xf8;
    vram[20] = 0xe0;
    vram[21] = 0x07;
    vram[22] = 0x1f;
    vram[24] = 0xff;
    vram[25] = 0xff;
    memset(dst, 0, sizeof(dst));
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 2);
    assert(dst[2] == 0 && dst[7] == 0);
    assert(dst[3] == 0xff0000 && dst[4] == 0x00ff00);
    assert(dst[5] == 0x0000ff && dst[6] == 0xffffff);
    memset(dst, 0, sizeof(dst));
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 5, 2);
    assert(dst[3] == 0xff0000 && dst[4] == 0x00ff00 && dst[5] == 0);

    /* Manual buffer 2, 2x vertical replication, and row clipping. */
    cr[0x59] = 8;
    cr[0x5e] = 0x10;
    cr[0x32] = 128;
    cr[0x3e] |= 0x10;
    assert(cirrus_overlay_decode(cr, 16, &w));
    assert(w.base == 34 && w.vertical_step == 128);
    vram[35] = 0xf8;
    memset(dst, 0, sizeof(dst));
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 3);
    assert(dst[3] == 0xff0000);
    memset(dst, 0, sizeof(dst));
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 4);
    assert(dst[3] == 0);

    /* A source row outside real VRAM must leave the primary intact. */
    w.base = sizeof(vram) - 2;
    memset(dst, 0x5a, sizeof(dst));
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 2);
    assert(dst[3] == 0x5a5a5a5a);

    /* Unsupported modes must not silently render a different format. */
    cr[0x3e] |= 0x80;
    assert(!cirrus_overlay_decode(cr, 16, &w));
    cr[0x3e] &= ~0x80;
    cr[0x31] = 128;
    assert(!cirrus_overlay_decode(cr, 16, &w));
    cr[0x31] = 0;
    cr[0x5e] = 0x20;
    assert(!cirrus_overlay_decode(cr, 16, &w));

    /* YUV reference vectors and distinct normal/planar byte orders. */
    assert(cirrus_overlay_yuv(16, 128, 128) == 0);
    assert(cirrus_overlay_yuv(235, 128, 128) == 0xffffff);
    assert(cirrus_overlay_rgb(0x7c00, false) == 0xff0000);
    memset(cr, 0, sizeof(cr));
    cr[0x34] = 1;
    cr[0x35] = 1;
    cr[0x38] = 1;
    cr[0x3d] = 1;
    cr[0x3e] = 1;
    assert(cirrus_overlay_decode(cr, 16, &w));
    vram[0] = 128;
    vram[1] = 16;
    vram[2] = 128;
    vram[3] = 235;
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 0);
    assert(dst[0] == 0 && dst[1] == 0xffffff);
    cr[0x3f] = 0x10;
    assert(cirrus_overlay_decode(cr, 16, &w));
    vram[0] = 128;
    vram[1] = 128;
    vram[2] = 235;
    vram[3] = 16;
    cirrus_overlay_draw(&w, vram, sizeof(vram), dst, 8, 0);
    assert(dst[0] == 0 && dst[1] == 0xffffff);
    return 0;
}
