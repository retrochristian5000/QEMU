/* SPDX-License-Identifier: GPL-2.0-or-later */
/* Read-only inspection of the Apple Core99 parameter-bank format. */
#include "qemu/osdep.h"
#include "hw/nvram/core99_bank.h"

#define ADLER_OFFSET 0x10
#define GENERATION_OFFSET 0x14
#define ADLER_MOD 65521U

static uint32_t read_be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | p[3];
}

static uint8_t header_sum(const uint8_t *bank)
{
    unsigned sum = 0;

    for (unsigned i = 0; i < ADLER_OFFSET; i++) {
        if (i != 1) {
            sum += bank[i];
        }
    }
    return sum ? (sum - 1) % 255 + 1 : 0;
}

static uint32_t bank_adler(const uint8_t *bank, bool legacy)
{
    uint32_t a = 1, b = 0;

    for (unsigned i = GENERATION_OFFSET; i < CORE99_FLASH_BANK_SIZE; i++) {
        /* Historical Linux reduces only the high sum every 5000 bytes.
         * Preserve its unsigned wrap for recognition, not image creation. */
        if (legacy && (i - GENERATION_OFFSET) % 5000 == 0) {
            b %= ADLER_MOD;
        }
        a += bank[i];
        b += a;
        if (!legacy) {
            a %= ADLER_MOD;
            b %= ADLER_MOD;
        }
    }
    return ((b % ADLER_MOD) << 16) | (a % ADLER_MOD);
}

Core99BankInfo core99_bank_inspect(const uint8_t bank[CORE99_FLASH_BANK_SIZE])
{
    Core99BankInfo info = { .status = CORE99_BANK_BAD_SIGNATURE };
    uint32_t stored;

    if (bank[0] != 0x5a) {
        return info;
    }
    info.status = CORE99_BANK_BAD_HEADER;
    if (bank[1] != header_sum(bank)) {
        return info;
    }
    info.status = CORE99_BANK_BAD_ADLER;
    stored = read_be32(bank + ADLER_OFFSET);
    if (stored == bank_adler(bank, false)) {
        info.status = CORE99_BANK_VALID;
    } else if (stored == bank_adler(bank, true)) {
        info.status = CORE99_BANK_LEGACY_ADLER;
    } else {
        return info;
    }
    info.generation = read_be32(bank + GENERATION_OFFSET);
    return info;
}

static bool bank_valid(Core99BankStatus status)
{
    return status == CORE99_BANK_VALID || status == CORE99_BANK_LEGACY_ADLER;
}

int core99_bank_select(const Core99BankInfo banks[2])
{
    if (!bank_valid(banks[0].status)) {
        return bank_valid(banks[1].status) ? 1 : -1;
    }
    if (!bank_valid(banks[1].status)) {
        return 0;
    }
    return banks[1].generation > banks[0].generation ? 1 : 0;
}
