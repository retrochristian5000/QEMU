/*
 * WHP host laptop battery -> SeaBIOS APM 1.2 POST snapshot.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * The eight-byte wire format is versioned and has no native alignment.
 * Deliberately read-only; a real APM battery interface must not allow
 * guest software to change the host's power controls.
 */
#ifndef HW_I386_HOST_BATTERY_H
#define HW_I386_HOST_BATTERY_H

#include <stdbool.h>
#include <stdint.h>

#define WHP_APM_FILE "opt/org.seabios/whp-laptop-apm"
#define WHP_APM_WIRE_SIZE 8

typedef struct WHPHostBattery {
    bool present;
    int ac_line;           /* 0 battery, 1 AC, 0xff unknown */
    int percentage;        /* 0..100, or -1 unknown */
    bool charging;
    int remaining_minutes; /* 0..32766, or -1 unknown */
} WHPHostBattery;

static inline bool whp_host_battery_encode(const WHPHostBattery *host,
                                           uint8_t wire[WHP_APM_WIRE_SIZE])
{
    if (!host || !wire || !host->present ||
        (host->ac_line != 0 && host->ac_line != 1 &&
         host->ac_line != 0xff) ||
        (host->percentage != -1 &&
         (host->percentage < 0 || host->percentage > 100)) ||
        (host->remaining_minutes != -1 &&
         (host->remaining_minutes < 0 || host->remaining_minutes > 32766))) {
        return false;
    }

    uint8_t status = 0xff, flags = 0xff;
    if (host->charging) {
        status = 3;
        flags = 0x08;
    } else if (host->percentage >= 0) {
        status = host->percentage <= 5 ? 2 :
                 host->percentage <= 20 ? 1 : 0;
        flags = 1u << status;
    }

    uint16_t time = 0xffff;
    if (!host->charging && host->ac_line == 0 &&
        host->remaining_minutes >= 0) {
        time = 0x8000u | host->remaining_minutes;
    }
    wire[0] = 1;            /* protocol version */
    wire[1] = host->ac_line;
    wire[2] = status;
    wire[3] = flags;
    wire[4] = host->percentage < 0 ? 0xff : host->percentage;
    wire[5] = 1;            /* one internal battery, not UPS */
    wire[6] = time & 0xff;
    wire[7] = time >> 8;
    return true;
}

/* Read one actual internal host battery. No synthetic battery on desktops. */
bool whp_host_battery_read(WHPHostBattery *out);

#endif
