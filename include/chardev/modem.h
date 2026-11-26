/*
 * Reset input for QEMU's Hayes-compatible serial modem substitute.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_CHARDEV_MODEM_H
#define QEMU_CHARDEV_MODEM_H

#include "chardev/char.h"

/* Create a registered modem backend with no simulated telephone line. */
Chardev *qemu_modem_new_offline(const char *model, Error **errp);

/* Physical modem reset GPIO has been asserted; BQL must be held. */
void qemu_modem_hardware_reset(Chardev *chr);

/* Read-only host observation of the external modem front panel. */
typedef enum ModemIndicator {
    MODEM_LED_TST = 1 << 0,
    MODEM_LED_HS  = 1 << 1,
    MODEM_LED_EC  = 1 << 2,
    MODEM_LED_CD  = 1 << 3,
    MODEM_LED_OH  = 1 << 4,
    MODEM_LED_RD  = 1 << 5,
    MODEM_LED_SD  = 1 << 6,
    MODEM_LED_TR  = 1 << 7,
    MODEM_LED_MR  = 1 << 8,
} ModemIndicator;

typedef struct ModemIndicatorSnapshot {
    char *id;
    char *model;
    unsigned supported;
    unsigned active;
    unsigned rx_events;
    unsigned tx_events;
} ModemIndicatorSnapshot;

/*
 * Caller holds BQL. Returns an owned array of copied snapshots, including
 * automatically created ISA modem backends. Free with g_ptr_array_unref().
 * Activity counters wrap naturally; no frontend timing is emulated here.
 */
GPtrArray *qemu_modem_indicator_snapshot(void);

#endif
