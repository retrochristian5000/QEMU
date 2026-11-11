/*
 * Host-side libFuzzer target for TriMedia compressed instruction bytes.
 * Incoming data is untrusted guest code; no guest execution is attempted.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "packet.h"
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>

static void invariant(bool condition)
{
    if (!condition) {
        abort();
    }
}

int LLVMFuzzerTestOneInput(const uint8_t *data, size_t size)
{
    TrimediaPacketLayout packet;
    uint16_t format;
    const uint8_t *stream;
    size_t available;
    bool decoded;
    unsigned int operations = 0;

    if (size < 2) {
        return 0;
    }

    format = (uint16_t)data[0] | ((uint16_t)data[1] << 8);
    stream = data + 2;
    available = size - 2;
    decoded = trimedia_unpack_packet(stream, available, format, &packet);

    if (!decoded) {
        invariant(packet.encoded_size == 0);
        invariant(packet.num_ops == 0);
        return 0;
    }
    invariant(packet.encoded_size <= available);
    invariant(packet.encoded_size >= 2);
    invariant(packet.encoded_size <= TRIMEDIA_PACKET_MAX_BYTES);
    invariant(packet.input_format == format);
    invariant(packet.following_format ==
              ((uint16_t)stream[0] | ((uint16_t)stream[1] << 8)));

    for (unsigned int slot = 0; slot < TRIMEDIA_PACKET_SLOTS; ++slot) {
        const TrimediaPackedSlot *op = &packet.slots[slot];
        unsigned int code = (format >> (2 * slot)) & 3;

        invariant(op->present == (code != 3));
        if (!op->present) {
            invariant(op->encoded_bits == 0);
            invariant(op->raw_operation == 0);
            continue;
        }
        ++operations;
        invariant(op->encoded_bits == 26 + 8 * code);
        invariant(op->extension_bytes == code);
        invariant((size_t)op->core_byte_offset + 3 <= packet.encoded_size);
        if (code) {
            invariant((size_t)op->extension_byte_offset + code <=
                      packet.encoded_size);
        } else {
            invariant(op->extension_byte_offset == 0);
        }
        invariant(op->raw_operation < (UINT64_C(1) << op->encoded_bits));
    }
    invariant(packet.num_ops == operations);
    return 0;
}
