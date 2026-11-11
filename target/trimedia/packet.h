/* TriMedia compressed packet framing, not full ISA semantics.
 * SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef QEMU_TRIMEDIA_PACKET_H
#define QEMU_TRIMEDIA_PACKET_H
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#define TRIMEDIA_PACKET_SLOTS 5
#define TRIMEDIA_PACKET_MAX_BYTES 28
#define TRIMEDIA_PACKET_DTREE_FORMAT UINT16_C(0x02aa)

typedef struct TrimediaPackedSlot {
    bool present;
    uint8_t encoded_bits;         /* 26, 34 or 42; zero for empty slot */
    uint8_t extension_bytes;      /* 0, 1 or 2 */
    uint8_t core_byte_offset;
    uint8_t extension_byte_offset;
    uint64_t raw_operation;       /* assembled compressed operation bits */
} TrimediaPackedSlot;

typedef struct TrimediaPacketLayout {
    uint16_t input_format;       /* comes from previous packet */
    uint16_t following_format;   /* first two bytes of this packet */
    uint8_t encoded_size;        /* 2..28 bytes */
    uint8_t num_ops;             /* 0..5 */
    TrimediaPackedSlot slots[TRIMEDIA_PACKET_SLOTS];
} TrimediaPacketLayout;

/* Supplying input_format is mandatory; never infer it from arbitrary PC. */
bool trimedia_unpack_packet(const uint8_t *stream, size_t available,
                            uint16_t input_format, TrimediaPacketLayout *out);
#endif
