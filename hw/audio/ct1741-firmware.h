/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_AUDIO_CT1741_FIRMWARE_H
#define HW_AUDIO_CT1741_FIRMWARE_H

#include "qapi/error.h"

typedef struct CT1741Firmware CT1741Firmware;

/* Private firmware/hardware ABI v1, documented by X86-Firmware. */
enum {
    CT1741_ACTION_RATE = 1,
    CT1741_ACTION_TIME_CONST,
    CT1741_ACTION_BLOCK,
    CT1741_ACTION_START,
    CT1741_ACTION_LEGACY_START,
    CT1741_ACTION_DMA_CONTROL,
    CT1741_ACTION_SPEAKER,
    CT1741_ACTION_IRQ,
    CT1741_ACTION_DMA_ID,
    CT1741_ACTION_DIRECT_DAC,
};
typedef void (*CT1741Action)(void *opaque, uint8_t action,
                             const uint8_t args[4]);
CT1741Firmware *ct1741_fw_new(const char *filename, const char *model,
                              CT1741Action action, void *opaque,
                              Error **errp);
void ct1741_fw_free(CT1741Firmware *s);
void ct1741_fw_reset(CT1741Firmware *s, bool asserted);
void ct1741_fw_write(CT1741Firmware *s, uint8_t value);
uint8_t ct1741_fw_read(CT1741Firmware *s);
bool ct1741_fw_busy(CT1741Firmware *s);
bool ct1741_fw_ready(CT1741Firmware *s);

#endif
