/*
 * ITU-T V.42bis transparent-mode escape primitives.
 * SPDX-License-Identifier: MIT
 */
#ifndef QEMU_CHARDEV_MODEM_V42BIS_H
#define QEMU_CHARDEV_MODEM_V42BIS_H

#include <stdbool.h>
#include <stdint.h>

typedef enum ModemV42bisToken {
    MODEM_V42BIS_MORE,
    MODEM_V42BIS_DATA,
    MODEM_V42BIS_RESET,
    MODEM_V42BIS_ECM,
    MODEM_V42BIS_INVALID,
} ModemV42bisToken;

typedef struct ModemV42bisTransparentRx {
    uint8_t escape;
    bool pending;
    bool stopped;
} ModemV42bisTransparentRx;

/* Initialize the transmit escape to zero at compression initialization. */
unsigned modem_v42bis_escape_encode(uint8_t *escape, uint8_t data,
                                     uint8_t wire[2]);

/* RESET uses the old escape value before restoring the initial value. */
void modem_v42bis_escape_reset(uint8_t *escape, uint8_t wire[2]);

/* Independent receive state, initialized at compression initialization. */
void modem_v42bis_transparent_init(ModemV42bisTransparentRx *rx);

/*
 * Consume one octet. DATA alone writes *data. MORE awaits a command
 * octet; RESET requests dictionary reinitialization. ECM is handed off
 * to the compressed-mode decoder. ECM and INVALID stop this primitive
 * until explicitly initialized again; neither is passed as user data.
 * This is not a dictionary implementation or a complete V.42bis codec.
 */
ModemV42bisToken modem_v42bis_transparent_decode(ModemV42bisTransparentRx *rx,
                                                 uint8_t wire, uint8_t *data);

#endif
