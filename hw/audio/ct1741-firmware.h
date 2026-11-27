/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_AUDIO_CT1741_FIRMWARE_H
#define HW_AUDIO_CT1741_FIRMWARE_H

#include "qapi/error.h"

typedef struct CT1741Firmware CT1741Firmware;
CT1741Firmware *ct1741_fw_new(const char *filename, const char *model,
                              Error **errp);
void ct1741_fw_free(CT1741Firmware *s);
void ct1741_fw_reset(CT1741Firmware *s, bool asserted);
void ct1741_fw_write(CT1741Firmware *s, uint8_t value);
uint8_t ct1741_fw_read(CT1741Firmware *s);
bool ct1741_fw_busy(CT1741Firmware *s);
bool ct1741_fw_ready(CT1741Firmware *s);

#endif
