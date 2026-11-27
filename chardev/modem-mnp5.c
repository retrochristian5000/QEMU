/*
 * MNP Class 5 rank-code primitives.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include "chardev/modem-mnp5.h"

/* Published MNP5 rank codeword table; no adaptive ranking state here. */
unsigned modem_mnp5_rank_encode(unsigned rank, uint16_t *code)
{
    unsigned header, bits;

    if (rank > MODEM_MNP5_FLUSH) {
        return 0;
    }
    if (rank >= 255) {
        *code = 0x7fe + (rank == MODEM_MNP5_FLUSH);
        return 11;
    }
    if (rank < 4) {
        *code = rank;
        return 4;
    }
    for (bits = 2; rank >= (2U << bits); bits++) {
        /* Find the highest set bit. */
    }
    header = bits;
    *code = (header << bits) | (rank - (1U << bits));
    return 3 + bits;
}

bool modem_mnp5_rank_decode(uint16_t code, unsigned length, unsigned *rank)
{
    unsigned header, bits, value;

    if (length < 4 || length > 11 || code >= (1U << length)) {
        return false;
    }
    header = code >> (length - 3);
    if (header < 2) {
        if (length != 4) {
            return false;
        }
        value = code;
    } else if (length == 11) {
        if (code != 0x7fe && code != 0x7ff) {
            return false;
        }
        value = code == 0x7fe ? 255 : MODEM_MNP5_FLUSH;
    } else {
        bits = header;
        if (length != 3 + bits ||
            (length == 10 && code == 0x3ff)) {
            return false;
        }
        value = (1U << bits) + (code & ((1U << bits) - 1));
    }
    *rank = value;
    return true;
}
