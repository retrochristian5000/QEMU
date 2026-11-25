/* SPDX-License-Identifier: MIT */
#ifndef HW_BLOCK_CDROM_SECTOR_H
#define HW_BLOCK_CDROM_SECTOR_H

#include <stdint.h>
#include <string.h>

enum {
    CDROM_MODE1_DATA_SIZE = 2048,
    CDROM_RAW_SECTOR_SIZE = 2352,
    CDROM_MODE1_DATA_OFFSET = 16,
    CDROM_XA_FORM2_DATA_SIZE = 2324,
};

typedef enum CdromSectorMatch {
    CDROM_SECTOR_MATCH,
    CDROM_SECTOR_MISMATCH,
    CDROM_SECTOR_RESERVED,
} CdromSectorMatch;

/* MMC READ CD byte 1, bits 4:2. The cooked image has Mode 1 semantics. */
static inline CdromSectorMatch cdrom_mode1_expected_type(uint8_t byte1)
{
    switch ((byte1 >> 2) & 7) {
    case 0: /* Any sector type */
    case 2: /* Mode 1 */
        return CDROM_SECTOR_MATCH;
    case 1: /* CD-DA */
    case 3: /* Mode 2 formless */
    case 4: /* Mode 2 Form 1 */
    case 5: /* Mode 2 Form 2 (e.g. VCD video) */
        return CDROM_SECTOR_MISMATCH;
    default:
        return CDROM_SECTOR_RESERVED;
    }
}

/*
 * Complete a synthetic Mode 1 sector whose payload is already at offset 16.
 * Retain the legacy binary MSF header and zero-filled EDC/ECC area. This
 * is not a faithful physical-sector encoder and cannot synthesize XA data.
 */
static inline void cdrom_synthesize_mode1_sector(uint8_t *buf, uint32_t lba)
{
    uint64_t frames = (uint64_t)lba + 150;

    buf[0] = 0;
    memset(buf + 1, 0xff, 10);
    buf[11] = 0;
    buf[12] = frames / (75 * 60);
    buf[13] = (frames / 75) % 60;
    buf[14] = frames % 75;
    buf[15] = 1;
    memset(buf + CDROM_MODE1_DATA_OFFSET + CDROM_MODE1_DATA_SIZE, 0,
           CDROM_RAW_SECTOR_SIZE - CDROM_MODE1_DATA_OFFSET -
           CDROM_MODE1_DATA_SIZE);
}

#endif
