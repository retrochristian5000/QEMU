/*
 * ITU-T V.42bis (01/90), sections 7.2, 7.8.3, 8 and 9.2.
 * Transparent-mode escape primitives, separate from dictionary state.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include "chardev/modem-v42bis.h"

enum {
    V42BIS_ECM = 0,
    V42BIS_EID = 1,
    V42BIS_RESET = 2,
    V42BIS_ESCAPE_INCREMENT = 51,
};

static uint8_t v42bis_next_escape(uint8_t escape)
{
    return (uint8_t)(escape + V42BIS_ESCAPE_INCREMENT);
}

unsigned modem_v42bis_escape_encode(uint8_t *escape, uint8_t data,
                                     uint8_t wire[2])
{
    wire[0] = data;
    if (data != *escape) {
        return 1;
    }
    wire[1] = V42BIS_EID;
    *escape = v42bis_next_escape(*escape);
    return 2;
}

void modem_v42bis_escape_reset(uint8_t *escape, uint8_t wire[2])
{
    wire[0] = *escape;
    wire[1] = V42BIS_RESET;
    *escape = 0;
}

void modem_v42bis_transparent_init(ModemV42bisTransparentRx *rx)
{
    *rx = (ModemV42bisTransparentRx) { 0 };
}

ModemV42bisToken modem_v42bis_transparent_decode(ModemV42bisTransparentRx *rx,
                                                 uint8_t wire, uint8_t *data)
{
    if (rx->stopped) {
        return MODEM_V42BIS_INVALID;
    }

    if (!rx->pending) {
        if (wire == rx->escape) {
            rx->pending = true;
            return MODEM_V42BIS_MORE;
        }
        *data = wire;
        return MODEM_V42BIS_DATA;
    }

    rx->pending = false;
    switch (wire) {
    case V42BIS_EID:
        *data = rx->escape;
        rx->escape = v42bis_next_escape(rx->escape);
        return MODEM_V42BIS_DATA;
    case V42BIS_RESET:
        modem_v42bis_transparent_init(rx);
        return MODEM_V42BIS_RESET;
    case V42BIS_ECM:
        rx->stopped = true;
        return MODEM_V42BIS_ECM;
    default:
        rx->stopped = true;
        return MODEM_V42BIS_INVALID;
    }
}
