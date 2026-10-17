/* Philips TriMedia 26/34/42-bit operation layout and unpacking.
 * See US5787302 and PNX1300 Series Data Book. No execution is enabled.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#include "qemu/osdep.h"
#include "packet.h"

bool trimedia_unpack_packet(const uint8_t *stream, size_t available,
                            uint16_t input_format, TrimediaPacketLayout *out)
{
    TrimediaPacketLayout p = { 0 };
    unsigned int n = 0, exts = 0, total, core, ext, ordinal = 0;

    if (!out) {
        return false;
    }
    memset(out, 0, sizeof(*out));
    if (!stream || available < 2) {
        return false;
    }
    for (unsigned int slot = 0; slot < TRIMEDIA_PACKET_SLOTS; ++slot) {
        unsigned int code = (input_format >> (2 * slot)) & 3;
        TrimediaPackedSlot *s = &p.slots[slot];

        if (code == 3) {
            continue;
        }
        s->present = true;
        s->encoded_bits = 26 + 8 * code;
        s->extension_bytes = code;
        n++;
        exts += code;
    }

    /* First format group: two bytes. Second group is one extra byte
     * before the fourth occupied operation. Extensions trail the cores. */
    total = 2 + 3 * n + (n > 3 ? 1 : 0) + exts;
    if (total > TRIMEDIA_PACKET_MAX_BYTES || available < total) {
        return false;
    }
    p.input_format = input_format;
    p.following_format = (uint16_t)stream[0] | ((uint16_t)stream[1] << 8);
    p.encoded_size = total;
    p.num_ops = n;

    core = 2;
    ext = 2 + 3 * n + (n > 3 ? 1 : 0);
    for (unsigned int slot = 0; slot < TRIMEDIA_PACKET_SLOTS; ++slot) {
        TrimediaPackedSlot *s = &p.slots[slot];
        unsigned int top, low, extension = 0;

        if (!s->present) {
            continue;
        }
        if (ordinal == 3) {
            core++; /* second format group */
        }
        s->core_byte_offset = core;
        s->extension_byte_offset = s->extension_bytes ? ext : 0;
        low = ((unsigned int)stream[core] << 16) |
              ((unsigned int)stream[core + 1] << 8) | stream[core + 2];
        top = ordinal < 3 ?
              ((stream[1] >> (6 - 2 * ordinal)) & 3) :
              ((stream[11] >> (6 - 2 * (ordinal - 3))) & 3);
        if (s->extension_bytes) {
            extension = stream[ext];
            if (s->extension_bytes == 2) {
                extension |= (unsigned int)stream[ext + 1] << 8;
            }
        }
        s->raw_operation = (uint64_t)low |
                           ((uint64_t)top << 24) |
                           ((uint64_t)extension << 26);
        core += 3;
        ext += s->extension_bytes;
        ordinal++;
    }
    *out = p;
    return true;
}
