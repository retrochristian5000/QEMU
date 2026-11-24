/* SPDX-License-Identifier: GPL-2.0-or-later */
/*
 * Core99 NVRAM parameter-bank flash command engine.
 *
 * Implements the byte program and bank erase protocols used by the Linux
 * PowerMac NVRAM driver (Sharp/Micron and AMD command families). This is
 * not a full CFI device: chip IDs, protection pins, timed operations and
 * suspend/resume require a verified board-specific flash model.
 */
#include "qemu/osdep.h"
#include "hw/nvram/core99_flash.h"

#define SM_READY 0x80
#define SM_ERASE_ERROR 0x20
#define SM_PROGRAM_ERROR 0x10
#define AMD_DQ5 0x20
#define AMD_DQ6 0x40
#define AMD_DQ7 0x80
#define AMD_UNLOCK_1 0x555
#define AMD_UNLOCK_2 0x2aa
#define AMD_UNLOCK_MASK 0x7ff

static uint32_t bank_base(uint32_t addr)
{
    return addr & ~(CORE99_FLASH_BANK_SIZE - 1);
}

void core99_flash_reset(Core99Flash *s, Core99FlashProtocol protocol)
{
    *s = (Core99Flash) {
        .protocol = protocol,
        .phase = CORE99_FLASH_ARRAY,
        .status = SM_READY,
    };
}

uint8_t core99_flash_read(Core99Flash *s, const uint8_t *data, uint32_t addr)
{
    if (addr >= CORE99_FLASH_SIZE) {
        return 0xff;
    }
    if (s->phase == CORE99_FLASH_STATUS) {
        return s->status;
    }
    if (s->phase == CORE99_FLASH_AMD_FAILED) {
        s->toggle ^= AMD_DQ6;
        return AMD_DQ5 | s->toggle | (~s->failed_data & AMD_DQ7);
    }
    return data[addr];
}

static Core99FlashChange sm_write(Core99Flash *s, uint8_t *data,
                                  uint32_t addr, uint8_t value)
{
    /* A pending program consumes the next byte as data, even 0xff. */
    if (s->phase == CORE99_FLASH_PROGRAM) {
        if ((data[addr] & value) != value) {
            s->status |= SM_PROGRAM_ERROR;
        }
        data[addr] &= value;
        s->phase = CORE99_FLASH_STATUS;
        return CORE99_FLASH_PROGRAMMED;
    }
    if (s->phase == CORE99_FLASH_ERASE_CONFIRM) {
        if (value == 0xd0 && bank_base(addr) == s->erase_bank) {
            memset(data + s->erase_bank, 0xff, CORE99_FLASH_BANK_SIZE);
            s->phase = CORE99_FLASH_STATUS;
            return CORE99_FLASH_ERASED;
        }
        s->phase = CORE99_FLASH_STATUS;
        s->status |= SM_ERASE_ERROR | SM_PROGRAM_ERROR;
        return CORE99_FLASH_UNCHANGED;
    }

    switch (value) {
    case 0xff:
        s->phase = CORE99_FLASH_ARRAY;
        break;
    case 0x10:
    case 0x40:
        s->phase = CORE99_FLASH_PROGRAM;
        break;
    case 0x20:
        s->erase_bank = bank_base(addr);
        s->phase = CORE99_FLASH_ERASE_CONFIRM;
        break;
    case 0x50:
        s->status = SM_READY;
        break;
    case 0x70:
        s->phase = CORE99_FLASH_STATUS;
        break;
    default:
        break;
    }
    return CORE99_FLASH_UNCHANGED;
}

static Core99FlashChange amd_write(Core99Flash *s, uint8_t *data,
                                   uint32_t addr, uint8_t value)
{
    uint32_t cmd_addr = addr & AMD_UNLOCK_MASK;

    /* Program data takes precedence over command decoding. */
    if (s->phase == CORE99_FLASH_PROGRAM) {
        bool failed = (data[addr] & value) != value;

        data[addr] &= value;
        s->phase = failed ? CORE99_FLASH_AMD_FAILED : CORE99_FLASH_ARRAY;
        s->failed_data = value;
        s->toggle = 0;
        return CORE99_FLASH_PROGRAMMED;
    }
    if (value == 0xf0) {
        core99_flash_reset(s, CORE99_FLASH_AMD);
        return CORE99_FLASH_UNCHANGED;
    }

    switch (s->phase) {
    case CORE99_FLASH_ARRAY:
        if (cmd_addr == AMD_UNLOCK_1 && value == 0xaa) {
            s->phase = CORE99_FLASH_UNLOCK_2;
        }
        break;
    case CORE99_FLASH_UNLOCK_2:
        s->phase = cmd_addr == AMD_UNLOCK_2 && value == 0x55 ?
                   CORE99_FLASH_UNLOCK_COMMAND : CORE99_FLASH_ARRAY;
        break;
    case CORE99_FLASH_UNLOCK_COMMAND:
        s->phase = CORE99_FLASH_ARRAY;
        if (cmd_addr == AMD_UNLOCK_1) {
            if (value == 0xa0) {
                s->phase = CORE99_FLASH_PROGRAM;
            } else if (value == 0x80) {
                s->phase = CORE99_FLASH_ERASE_UNLOCK_1;
            }
        }
        break;
    case CORE99_FLASH_ERASE_UNLOCK_1:
        s->phase = cmd_addr == AMD_UNLOCK_1 && value == 0xaa ?
                   CORE99_FLASH_ERASE_UNLOCK_2 : CORE99_FLASH_ARRAY;
        break;
    case CORE99_FLASH_ERASE_UNLOCK_2:
        s->phase = cmd_addr == AMD_UNLOCK_2 && value == 0x55 ?
                   CORE99_FLASH_ERASE_CONFIRM : CORE99_FLASH_ARRAY;
        break;
    case CORE99_FLASH_ERASE_CONFIRM:
        s->phase = CORE99_FLASH_ARRAY;
        if (value == 0x30) {
            memset(data + bank_base(addr), 0xff, CORE99_FLASH_BANK_SIZE);
            return CORE99_FLASH_ERASED;
        }
        /* Chip erase is intentionally unsupported: protect the boot ROM. */
        break;
    case CORE99_FLASH_AMD_FAILED:
        break;
    default:
        s->phase = CORE99_FLASH_ARRAY;
        break;
    }
    return CORE99_FLASH_UNCHANGED;
}

Core99FlashChange core99_flash_write(Core99Flash *s, uint8_t *data,
                                     uint32_t addr, uint8_t value)
{
    if (addr >= CORE99_FLASH_SIZE) {
        return CORE99_FLASH_UNCHANGED;
    }

    switch (s->protocol) {
    case CORE99_FLASH_SHARP_MICRON:
        return sm_write(s, data, addr, value);
    case CORE99_FLASH_AMD:
        return amd_write(s, data, addr, value);
    default:
        return CORE99_FLASH_UNCHANGED;
    }
}
