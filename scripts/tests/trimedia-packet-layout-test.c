/* Test compressed-packet framing with public tinytest example and
 * all 1024 format combinations. SPDX-License-Identifier: GPL-2.0-or-later */
#include "packet.h"
#include <assert.h>
#include <stdint.h>
#include <stdio.h>

static const uint8_t tinytest[] = {
    0x7c,0x47,0x81,0x43,0x60,0x21,0x60,0xa0,0x85,0x50,0x80,0x30,
    0x03,0xc1,0x08,0x00,0x40,0xe0,0x60,0x45,0x60,0x11,0x40,0x0f,
    0x80,0x00,0x57,0x01,0xd5,0x43,0x21,0x51,0x88,0x08,0x83,0x68,
    0xc1,0xd7,0x21,0x21,0x83,0x68,0x01,0x81,0x28,0x06,0x04,0x22,
    0xc1,0x95,0xc1,0xfc,0xa7,0xa2,0x11,0xa2,0x22,0x01,0x22,0x07,
    0x00,0xa0,0x95,0x95,0xfe,0xff,0x02,0x07,0xe0,0xa1,0xfc,0x43,
    0x07,0x00,0xa2,0x7e,0x01,0xaa,0x82,0x08,0x11,0x02
};
int main(void)
{
    TrimediaPacketLayout p;
    uint16_t fmt = TRIMEDIA_PACKET_DTREE_FORMAT;
    static const unsigned int sizes[] = {28, 9, 14, 14, 5, 7, 5};
    unsigned int offset = 0;

    assert(sizeof(tinytest) == 82);
    for (unsigned int i = 0; i < 7; ++i) {
        assert(trimedia_unpack_packet(tinytest + offset,
                                     sizeof(tinytest) - offset, fmt, &p));
        assert(p.encoded_size == sizes[i]);
        fmt = p.following_format;
        if (i == 0) {
            assert(fmt == 0x477c && p.num_ops == 5);
            for (unsigned int j = 0; j < 5; ++j) {
                assert(p.slots[j].encoded_bits == 42);
                assert(p.slots[j].core_byte_offset == 2 + 3*j + (j >= 3));
                assert(p.slots[j].extension_byte_offset == 18 + j*2);
            }
            /*
             * Public tinytest first op: asli(7) r1 -> r34, guarded
             * by r1. Verify full operation fields, not just length.
             */
            assert(p.slots[0].raw_operation ==
                   ((UINT64_C(0x4560) << 26) | (UINT64_C(1) << 24) |
                    UINT64_C(0x604381)));
            assert(((p.slots[0].raw_operation >> 21) & 0xff) == 11);
            assert(((p.slots[0].raw_operation >> 14) & 0x7f) == 1);
            assert(((p.slots[0].raw_operation >> 7) & 0x7f) == 7);
            assert((p.slots[0].raw_operation & 0x7f) == 1);
            assert(((p.slots[0].raw_operation >> 35) & 0x7f) == 34);
        } else if (i == 1) {
            assert(p.num_ops == 2 && p.slots[0].encoded_bits == 26);
            assert(!p.slots[1].present && !p.slots[2].present);
            assert(p.slots[3].encoded_bits == 34 && !p.slots[4].present);
        }
        offset += sizes[i];
    }
    assert(offset == sizeof(tinytest));
    for (unsigned int f = 0; f < 1024; ++f) {
        uint8_t buffer[TRIMEDIA_PACKET_MAX_BYTES] = {0xa5, 0x56};
        unsigned int ops = 0, ext = 0, next_core = 2, next_ext, ordinal = 0;
        for (unsigned int s = 0; s < 5; ++s) {
            unsigned int code = (f >> (s * 2)) & 3;
            if (code < 3) {
                ++ops;
                ext += code;
            }
        }
        unsigned int size = 2 + 3 * ops + (ops > 3) + ext;
        assert(size >= 2 && size <= 28);
        assert(trimedia_unpack_packet(buffer, size, f, &p));
        assert(p.encoded_size == size && p.num_ops == ops);
        assert(p.following_format == 0x56a5);
        next_ext = 2 + 3 * ops + (ops > 3);
        for (unsigned int s = 0; s < 5; ++s) {
            unsigned int code = (f >> (2 * s)) & 3;
            TrimediaPackedSlot *slot = &p.slots[s];
            assert(slot->present == (code < 3));
            if (code == 3) {
                assert(slot->encoded_bits == 0);
                continue;
            }
            if (ordinal == 3) {
                next_core++;
            }
            assert(slot->encoded_bits == 26 + 8 * code);
            assert(slot->core_byte_offset == next_core);
            if (code) {
                assert(slot->extension_byte_offset == next_ext);
            }
            assert(slot->raw_operation < (UINT64_C(1) << (26 + 8*code)));
            next_core += 3;
            next_ext += code;
            ordinal++;
        }
        assert(next_ext == size);
        assert(!trimedia_unpack_packet(buffer, size - 1, f, &p));
        assert(p.encoded_size == 0);
    }
    assert(!trimedia_unpack_packet(NULL, 28, 0x02aa, &p));
    assert(!trimedia_unpack_packet(tinytest, 28, 0x02aa, NULL));
    assert(!trimedia_unpack_packet(tinytest, 1, 0x02aa, &p));
    puts("TriMedia packet unpacker: public sample and 1024 layouts PASS");
    return 0;
}
