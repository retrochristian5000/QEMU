/*
 * QEMU shared DVD-ROM structure responses
 *
 * Copyright (c) 2006 Fabrice Bellard
 *
 * Permission is hereby granted, free of charge, to any person obtaining a copy
 * of this software and associated documentation files (the "Software"), to deal
 * in the Software without restriction, including without limitation the rights
 * to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
 * copies of the Software, and to permit persons to whom the Software is
 * furnished to do so, subject to the following conditions:
 *
 * The above copyright notice and this permission notice shall be included in
 * all copies or substantial portions of the Software.
 *
 * THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
 * IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
 * FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
 * THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
 * LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
 * OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
 * THE SOFTWARE.
 */

#include "qemu/osdep.h"
#include "qemu/bswap.h"
#include "hw/block/dvdrom.h"

/*
 * Build the existing synthetic single-layer DVD-ROM responses. Media
 * detection, command allocation length and sense delivery are transport
 * policy. The caller supplies a full response buffer, not the guest's
 * allocation length.
 */
int dvdrom_read_structure(uint64_t sectors, uint8_t layer, uint8_t format,
                          uint8_t *buf, size_t capacity)
{
    static const unsigned sizes[] = {
        [0x00] = 2048 + 4,
        [0x01] = 4 + 4,
        [0x03] = 188 + 4,
        [0x04] = 2048 + 4,
    };
    unsigned size, i;

    if (format == 0xff) {
        size = 4;
        for (i = 0; i < ARRAY_SIZE(sizes); i++) {
            if (sizes[i]) {
                size += 4;
            }
        }
    } else {
        /* BCA contents are not implemented. Preserve legacy format list. */
        if (format >= ARRAY_SIZE(sizes) || !sizes[format] || format == 3) {
            return -EINVAL;
        }
        size = sizes[format];
        if (format == 0) {
            if (layer != 0) {
                return -EINVAL;
            }
            if (!sectors) {
                return -ENOMEDIUM;
            }
        }
    }

    if (capacity < size) {
        return -ENOSPC;
    }
    memset(buf, 0, size);

    switch (format) {
    case 0x00:
        buf[4] = 1;   /* DVD-ROM, part version 1 */
        buf[5] = 0xf; /* 120 mm disc, minimum rate unspecified */
        buf[6] = 1;   /* One layer, read-only */
        /* Preserve synthetic sector addresses used by both transports. */
        stl_be_p(buf + 12, sectors - 1);
        stl_be_p(buf + 16, sectors - 1);
        break;
    case 0x01: /* No copyright or region restrictions */
    case 0x04: /* Disc manufacturing information, all zeros */
        break;
    case 0xff: {
        unsigned offset = 4;

        for (i = 0; i < ARRAY_SIZE(sizes); i++) {
            if (!sizes[i]) {
                continue;
            }
            buf[offset] = i;
            buf[offset + 1] = 0x40; /* Readable, not writable */
            stw_be_p(buf + offset + 2, sizes[i]);
            offset += 4;
        }
        break;
    }
    default:
        g_assert_not_reached();
    }

    stw_be_p(buf, size - 2);
    return size;
}
