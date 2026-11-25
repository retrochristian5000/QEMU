/* SPDX-License-Identifier: MIT */
#ifndef HW_CHAR_ESCC_INTERNAL_H
#define HW_CHAR_ESCC_INTERNAL_H

#include "hw/char/escc.h"

/* Controller-owned receive queue and interrupt delivery. */
void escc_queue_clear(ESCCChannelState *s);
void escc_queue_put(ESCCChannelState *s, int b);

/* Sun serial input-device protocols. */
void escc_sunkbd_command(ESCCChannelState *s, int val);
extern const QemuInputHandler escc_sunkbd_handler;
extern const QemuInputHandler escc_sunmouse_handler;

#endif
