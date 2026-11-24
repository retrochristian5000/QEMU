/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_NVRAM_CORE99_BANK_H
#define HW_NVRAM_CORE99_BANK_H

#include <stdint.h>
#include "hw/nvram/core99_flash.h"

typedef enum Core99BankStatus {
    CORE99_BANK_BAD_SIGNATURE,
    CORE99_BANK_BAD_HEADER,
    CORE99_BANK_BAD_ADLER,
    CORE99_BANK_VALID,
    CORE99_BANK_LEGACY_ADLER,
} Core99BankStatus;

typedef struct Core99BankInfo {
    Core99BankStatus status;
    uint32_t generation;
} Core99BankInfo;

/* Inspect a full 8 KiB bank without modifying it. */
Core99BankInfo core99_bank_inspect(const uint8_t bank[CORE99_FLASH_BANK_SIZE]);
/* Select a validated bank, or -1 if neither is valid. Ties select bank 0. */
int core99_bank_select(const Core99BankInfo banks[2]);

#endif
