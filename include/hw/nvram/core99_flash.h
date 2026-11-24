/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_NVRAM_CORE99_FLASH_H
#define HW_NVRAM_CORE99_FLASH_H

#include <stdint.h>

#define CORE99_FLASH_BANK_SIZE 0x2000
#define CORE99_FLASH_SIZE (2 * CORE99_FLASH_BANK_SIZE)

typedef enum Core99FlashProtocol {
    CORE99_FLASH_SHARP_MICRON,
    CORE99_FLASH_AMD,
} Core99FlashProtocol;

typedef enum Core99FlashPhase {
    CORE99_FLASH_ARRAY,
    CORE99_FLASH_STATUS,
    CORE99_FLASH_PROGRAM,
    CORE99_FLASH_ERASE_CONFIRM,
    CORE99_FLASH_UNLOCK_2,
    CORE99_FLASH_UNLOCK_COMMAND,
    CORE99_FLASH_ERASE_UNLOCK_1,
    CORE99_FLASH_ERASE_UNLOCK_2,
    CORE99_FLASH_AMD_FAILED,
} Core99FlashPhase;

typedef enum Core99FlashChange {
    CORE99_FLASH_UNCHANGED,
    CORE99_FLASH_PROGRAMMED,
    CORE99_FLASH_ERASED,
} Core99FlashChange;

typedef struct Core99Flash {
    Core99FlashProtocol protocol;
    Core99FlashPhase phase;
    uint32_t erase_bank;
    uint8_t status;
    uint8_t failed_data;
    uint8_t toggle;
} Core99Flash;

/*
 * Byte-wide command engine for the two Core99 parameter banks. The caller
 * owns the array and persists changes. PROGRAMMED changes the addressed
 * byte; ERASED changes the bank containing the confirmation address.
 * Operations complete synchronously. Reset preserves array contents.
 */
void core99_flash_reset(Core99Flash *s, Core99FlashProtocol protocol);
uint8_t core99_flash_read(Core99Flash *s, const uint8_t *data, uint32_t addr);
Core99FlashChange core99_flash_write(Core99Flash *s, uint8_t *data,
                                     uint32_t addr, uint8_t value);

#endif
