/* SPDX-License-Identifier: MIT */
#ifndef HW_BLOCK_MMC_ROM_H
#define HW_BLOCK_MMC_ROM_H

#include <stdint.h>
#include <string.h>
#include "scsi/constants.h"

enum {
    MMC_ROM_PROFILE_LIST_SIZE = 20,
    MMC_ROM_DISC_INFO_SIZE = 34,
};

/*
 * Construct a complete GET CONFIGURATION header and feature 0 for a
 * read-only CD/DVD drive. The caller supplies a full response buffer
 * and a current profile of NONE, CD_ROM or DVD_ROM, not a guest
 * allocation length. Transport-specific features may follow.
 */
static inline void mmc_rom_profile_list(uint8_t *buf, uint16_t current)
{
    memset(buf, 0, MMC_ROM_PROFILE_LIST_SIZE);
    buf[3] = MMC_ROM_PROFILE_LIST_SIZE - 4;
    buf[6] = current >> 8;
    buf[7] = current;
    buf[10] = 0x03; /* Persistent and current feature */
    buf[11] = 8;    /* Two four-byte profile descriptors */
    buf[13] = MMC_PROFILE_DVD_ROM;
    buf[14] = current == MMC_PROFILE_DVD_ROM;
    buf[17] = MMC_PROFILE_CD_ROM;
    buf[18] = current == MMC_PROFILE_CD_ROM;
}

/* Finalized, non-erasable, single-track cooked CD/DVD image. */
static inline void mmc_rom_disc_information(uint8_t *buf)
{
    memset(buf, 0, MMC_ROM_DISC_INFO_SIZE);
    buf[1] = MMC_ROM_DISC_INFO_SIZE - 2;
    buf[2] = 0x0e; /* Complete disc and last session; Erasable = 0 */
    buf[3] = 1;    /* First track */
    buf[4] = 1;    /* Sessions */
    buf[5] = 1;    /* First track of last session */
    buf[6] = 1;    /* Last track of last session */
    buf[7] = 0x20; /* Unrestricted use */
}

#endif
