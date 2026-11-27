/*
 * MNP Class 5 rank-code primitives.
 * SPDX-License-Identifier: MIT
 */
#ifndef QEMU_CHARDEV_MODEM_MNP5_H
#define QEMU_CHARDEV_MODEM_MNP5_H

#include <stdbool.h>
#include <stdint.h>

#define MODEM_MNP5_FLUSH 256

/*
 * Rank 0..255, or the flush token. Code is right-aligned; transmit its
 * most significant used bit first. Zero length indicates invalid rank.
 */
unsigned modem_mnp5_rank_encode(unsigned rank, uint16_t *code);

/*
 * Decode one complete, right-aligned codeword. On invalid length or
 * code return false without modifying rank. No stream state is changed.
 */
bool modem_mnp5_rank_decode(uint16_t code, unsigned length, unsigned *rank);

#endif
