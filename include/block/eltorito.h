/* SPDX-License-Identifier: MIT */
#ifndef BLOCK_ELTORITO_H
#define BLOCK_ELTORITO_H

#include <stdbool.h>
#include <stdint.h>
#include <string.h>

#define ELTORITO_BLOCK_SIZE 2048

typedef struct ElToritoInitialExtent {
    uint64_t offset;
    uint64_t bytes;
} ElToritoInitialExtent;

static inline uint32_t eltorito_le32(const uint8_t *p)
{
    return (uint32_t)p[0] | (uint32_t)p[1] << 8 |
           (uint32_t)p[2] << 16 | (uint32_t)p[3] << 24;
}

/* The caller provides a complete 2048-byte boot record. */
static inline bool eltorito_catalog_lba(const uint8_t *record,
                                        uint64_t image_size, uint32_t *lba)
{
    static const uint8_t system_id[32] = "EL TORITO SPECIFICATION";
    uint32_t value = eltorito_le32(record + 71);

    if (record[0] != 0 || memcmp(record + 1, "CD001", 5) ||
        record[6] != 1 || memcmp(record + 7, system_id, sizeof(system_id)) ||
        value < 18 || (uint64_t)value * ELTORITO_BLOCK_SIZE > image_size ||
        image_size - (uint64_t)value * ELTORITO_BLOCK_SIZE <
            ELTORITO_BLOCK_SIZE) {
        return false;
    }
    *lba = value;
    return true;
}

/* Bound advisory discovery; never walk directory records or path tables. */
#define ELTORITO_DESCRIPTOR_LIMIT 32

typedef enum ElToritoScanResult {
    ELTORITO_SCAN_FALLBACK,
    ELTORITO_SCAN_NO_BOOT,
    ELTORITO_SCAN_FOUND,
} ElToritoScanResult;

typedef bool (*ElToritoReadBlock)(void *opaque, uint32_t lba, uint8_t *buf);

static inline ElToritoScanResult
eltorito_scan_descriptors(ElToritoReadBlock read_block, void *opaque,
                         uint64_t image_size, uint8_t *block,
                         uint32_t *catalog_lba)
{
    for (uint32_t lba = 16; lba < 16 + ELTORITO_DESCRIPTOR_LIMIT; lba++) {
        if ((uint64_t)(lba + 1) * ELTORITO_BLOCK_SIZE > image_size ||
            !read_block(opaque, lba, block) ||
            memcmp(block + 1, "CD001", 5) || block[6] != 1) {
            return ELTORITO_SCAN_FALLBACK;
        }

        /* Require the ordinary primary descriptor at the start. */
        if (lba == 16 && block[0] != 1) {
            return ELTORITO_SCAN_FALLBACK;
        }

        switch (block[0]) {
        case 0:
            return eltorito_catalog_lba(block, image_size, catalog_lba) ?
                ELTORITO_SCAN_FOUND : ELTORITO_SCAN_FALLBACK;
        case 1: /* Primary hierarchy, including legacy naming conventions */
        case 2: /* Supplementary hierarchy, e.g. Joliet */
            break;
        case 255:
            return ELTORITO_SCAN_NO_BOOT;
        default:
            return ELTORITO_SCAN_FALLBACK;
        }
    }
    return ELTORITO_SCAN_FALLBACK;
}

/*
 * Conservative advisory fast path, not a complete El Torito parser.
 * Require a single x86 no-emulation entry and an otherwise empty catalog.
 * EFI, section entries and disk emulation need the full fallback.
 */
static inline bool eltorito_initial_extent(const uint8_t *cat,
                                          uint64_t image_size,
                                          ElToritoInitialExtent *extent)
{
    unsigned sum = 0;
    uint32_t lba = eltorito_le32(cat + 40);
    unsigned count = cat[38] | (unsigned)cat[39] << 8;
    uint64_t offset = (uint64_t)lba * ELTORITO_BLOCK_SIZE;
    uint64_t bytes = ((count + 3) / 4) * ELTORITO_BLOCK_SIZE;

    if (cat[0] != 1 || cat[1] != 0 || cat[30] != 0x55 ||
        cat[31] != 0xaa || cat[32] != 0x88 || cat[33] != 0 ||
        lba < 18 || !count || offset > image_size ||
        bytes > image_size - offset) {
        return false;
    }
    for (unsigned i = 0; i < 32; i += 2) {
        sum += cat[i] | (unsigned)cat[i + 1] << 8;
    }
    if (sum & 0xffff) {
        return false;
    }
    for (unsigned i = 64; i < ELTORITO_BLOCK_SIZE; i++) {
        if (cat[i]) {
            return false;
        }
    }
    extent->offset = offset;
    extent->bytes = bytes;
    return true;
}

#endif
