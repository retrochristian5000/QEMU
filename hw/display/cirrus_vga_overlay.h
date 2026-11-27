/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DISPLAY_CIRRUS_VGA_OVERLAY_H
#define HW_DISPLAY_CIRRUS_VGA_OVERLAY_H

#include <stdbool.h>
#include <stdint.h>

/* GD5446 TRM 6.1-6.14, 6.22-6.27: video window register masks. */
static inline uint8_t cirrus_overlay_reg_mask(unsigned index)
{
    switch (index) {
    case 0x31 ... 0x35:
    case 0x37 ... 0x38:
    case 0x3a ... 0x3b:
    case 0x3d:
    case 0x59 ... 0x5a:
        return 0xff;
    case 0x36:
    case 0x5d:
        return 0x3f;
    case 0x39:
        return 0x0f;
    case 0x3c:
        return 0x2f;
    case 0x3e:
        return 0xbf;
    case 0x3f:
        return 0x33; /* VREF, field ID and capture buffer are read-only. */
    case 0x58:
        return 0x6f;
    case 0x5e:
        return 0x37;
    default:
        return 0;
    }
}

typedef struct CirrusOverlay {
    unsigned x, width, top, bottom;
    unsigned base, pitch, source_bytes;
    unsigned format;
    unsigned vertical_step;
    bool planar;
} CirrusOverlay;

/*
 * TRM 9.5.2-9.5.5: positions are in graphics DWORDs, not video pixels.
 * This renderer supports rectangular unscaled horizontal playback and
 * either unscaled or replicated vertical lines, with manual buffer select.
 * Do not substitute incorrect pixels for unsupported modes.
 */
static inline bool cirrus_overlay_decode(const uint8_t *cr, unsigned depth,
                                         CirrusOverlay *w)
{
    unsigned bytes, left, width, select = (cr[0x5e] >> 4) & 3;
    unsigned format = (cr[0x3e] >> 1) & 7;
    unsigned required;

    if (!(cr[0x3e] & 1) || (cr[0x3e] & 0x80) || cr[0x31] ||
        select >= 2 || (format != 0 && format != 1 &&
                        format != 4 && format != 5) ||
        (format != 0 && (cr[0x3f] & 0x10))) {
        return false;
    }
    if (cr[0x32] && (cr[0x32] < 64 || !(cr[0x3e] & 0x10))) {
        return false;
    }
    if (depth != 8 && depth != 15 && depth != 16) {
        return false;
    }

    bytes = (depth + 7) / 8;
    left = 4 * (cr[0x33] | ((cr[0x36] & 3) << 8)) + (cr[0x5d] & 3);
    width = 4 * (cr[0x34] | ((cr[0x36] & 0x0c) << 6)) +
            ((cr[0x5d] >> 4) & 3);
    if (left % bytes || width % bytes) {
        return false;
    }

    w->x = left / bytes;
    w->width = width / bytes;
    w->top = cr[0x37] | ((cr[0x39] & 3) << 8);
    w->bottom = cr[0x38] | ((cr[0x39] & 0x0c) << 6);
    w->source_bytes = 4 * (cr[0x35] | ((cr[0x36] & 0x30) << 4));
    w->pitch = (cr[0x3d] << 3) | ((cr[0x3c] & 0x20) << 6);
    w->format = format;
    w->vertical_step = cr[0x32] ? cr[0x32] : 256;
    w->planar = !!(cr[0x3f] & 0x10);
    if (select) {
        w->base = ((cr[0x58] & 0x0f) << 18) |
                  (cr[0x5a] << 10) | (cr[0x59] << 2);
    } else {
        w->base = ((cr[0x3c] & 0x0f) << 18) |
                  (cr[0x3b] << 10) | (cr[0x3a] << 2);
    }
    w->base |= (cr[0x5d] >> 2) & 3;

    /* TRM 9.5.2: source fetches are DWORDs, including a partial packet. */
    required = format == 1 ? (w->width + 3) / 4 * 4 :
               format == 0 ? (w->width + 1) / 2 * 4 : w->width * 2;

    return w->width && w->bottom > w->top && w->source_bytes >= required;
}

static inline unsigned cirrus_overlay_clamp(int value)
{
    if (value <= 0) {
        return 0;
    }
    if (value >= 255 * 256) {
        return 255;
    }
    return value / 256;
}

static inline uint32_t cirrus_overlay_yuv(unsigned y, unsigned u, unsigned v)
{
    /* BT.601 limited-range conversion; chroma has an excess-128 bias. */
    int luma = 298 * ((int)y - 16);
    int cb = (int)u - 128;
    int cr = (int)v - 128;
    unsigned r = cirrus_overlay_clamp(luma + 409 * cr + 128);
    unsigned g = cirrus_overlay_clamp(luma - 100 * cb - 208 * cr + 128);
    unsigned b = cirrus_overlay_clamp(luma + 516 * cb + 128);

    return (r << 16) | (g << 8) | b;
}

static inline uint32_t cirrus_overlay_rgb(uint16_t pixel, bool rgb565)
{
    unsigned r = (pixel >> (rgb565 ? 11 : 10)) & 31;
    unsigned g = (pixel >> 5) & (rgb565 ? 63 : 31);
    unsigned b = pixel & 31;

    r = (r << 3) | (r >> 2);
    g = rgb565 ? (g << 2) | (g >> 4) : (g << 3) | (g >> 2);
    b = (b << 3) | (b >> 2);
    return (r << 16) | (g << 8) | b;
}

/*
 * TRM 9.3.2.4, figure 9-6: each little-endian DWORD contains Y3:Y2:Y1:Y0
 * (5 bits each), then U:V (6 bits each). The low sample bits are zero
 * padded, not DAC-expanded; preserve the CCIR601 chroma bias of 128.
 */
static inline uint32_t cirrus_accupak_load(const uint8_t *src)
{
    return (uint32_t)src[0] | ((uint32_t)src[1] << 8) |
           ((uint32_t)src[2] << 16) | ((uint32_t)src[3] << 24);
}

static inline unsigned cirrus_accupak_y(uint32_t packet, unsigned pixel)
{
    return ((packet >> (12 + 5 * (pixel & 3))) & 31) << 3;
}

static inline unsigned cirrus_accupak_u(uint32_t packet)
{
    return ((packet >> 6) & 63) << 2;
}

static inline unsigned cirrus_accupak_v(uint32_t packet)
{
    return (packet & 63) << 2;
}

/*
 * The manual specifies expansion to YUV422 followed by color conversion,
 * but not the exact interpolation rounding. Use linear quarter steps
 * between neighboring packets and extend the last chroma sample at the
 * source edge. Never sample padding or the next scanline.
 */
static inline void cirrus_accupak_draw(const uint8_t *src, uint32_t *dst,
                                       unsigned source_width,
                                       unsigned visible_width)
{
    for (unsigned x = 0; x < visible_width; x += 4) {
        uint32_t packet = cirrus_accupak_load(src + x);
        uint32_t next = x + 4 < source_width ?
                        cirrus_accupak_load(src + x + 4) : packet;
        unsigned u0 = cirrus_accupak_u(packet);
        unsigned v0 = cirrus_accupak_v(packet);
        unsigned u1 = cirrus_accupak_u(next);
        unsigned v1 = cirrus_accupak_v(next);

        for (unsigned i = 0; i < 4 && x + i < visible_width; i++) {
            unsigned u = (u0 * (4 - i) + u1 * i + 2) / 4;
            unsigned v = (v0 * (4 - i) + v1 * i + 2) / 4;

            dst[x + i] = cirrus_overlay_yuv(cirrus_accupak_y(packet, i),
                                            u, v);
        }
    }
}

/* Compose into an already rendered 32-bit host scanline, never into VRAM. */
static inline void cirrus_overlay_draw(const CirrusOverlay *w,
                                      const uint8_t *vram, unsigned vram_size,
                                      uint32_t *dst, unsigned screen_width,
                                      unsigned y)
{
    unsigned row, addr, width;
    const uint8_t *src;

    if (y < w->top || y > w->bottom || w->x >= screen_width) {
        return;
    }
    row = (y - w->top) * w->vertical_step / 256;
    addr = w->base + row * w->pitch;
    if (addr >= vram_size || w->source_bytes > vram_size - addr) {
        return;
    }
    width = w->width < screen_width - w->x ? w->width : screen_width - w->x;
    src = vram + addr;
    dst += w->x;

    if (w->format == 1) {
        cirrus_accupak_draw(src, dst, w->width, width);
        return;
    }

    for (unsigned x = 0; x < width; x++) {
        if (w->format == 0) {
            /* TRM 9.3.2.8-9: UYVY, or U V Y1 Y0 with planar assist. */
            unsigned pair = x / 2 * 4;
            unsigned u = src[pair];
            unsigned v = src[pair + (w->planar ? 1 : 2)];
            unsigned yy = src[pair + (w->planar ? 3 - (x & 1) :
                                                  1 + 2 * (x & 1))];

            /* Interpolate the missing chroma sample between pairs. */
            if ((x & 1) && pair + 4 < w->source_bytes &&
                x + 1 < w->width) {
                u = (u + src[pair + 4] + 1) / 2;
                v = (v + src[pair + 4 + (w->planar ? 1 : 2)] + 1) / 2;
            }
            dst[x] = cirrus_overlay_yuv(yy, u, v);
        } else {
            uint16_t pixel = src[2 * x] | (src[2 * x + 1] << 8);

            dst[x] = cirrus_overlay_rgb(pixel, w->format == 5);
        }
    }
}

#endif
