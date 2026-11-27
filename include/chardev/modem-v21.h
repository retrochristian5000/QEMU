/*
 * V.21 binary FSK signal primitives.
 * SPDX-License-Identifier: MIT
 */
#ifndef QEMU_CHARDEV_MODEM_V21_H
#define QEMU_CHARDEV_MODEM_V21_H

#include <stdbool.h>
#include <stdint.h>

#define MODEM_V21_BIT_RATE 300
#define MODEM_V21_SAMPLE_RATE 9600
#define MODEM_V21_SAMPLES_PER_BIT (MODEM_V21_SAMPLE_RATE / MODEM_V21_BIT_RATE)

typedef enum ModemV21Channel {
    MODEM_V21_CHANNEL_1,
    MODEM_V21_CHANNEL_2,
} ModemV21Channel;

typedef struct ModemV21Tx {
    ModemV21Channel channel;
    unsigned phase;
} ModemV21Tx;

/* Phase-continuous PCM, one bit per call. Caller supplies 32 samples. */
void modem_v21_tx_init(ModemV21Tx *tx, ModemV21Channel channel);
void modem_v21_tx_bit(ModemV21Tx *tx, bool bit,
                      int16_t samples[MODEM_V21_SAMPLES_PER_BIT]);

/*
 * Classify an already symbol-aligned PCM window (0, 1, or -1 for no
 * energy/ambiguous tones). Not a carrier or clock acquisition routine.
 */
int modem_v21_rx_bit(ModemV21Channel channel,
                     const int16_t samples[MODEM_V21_SAMPLES_PER_BIT]);

#endif
