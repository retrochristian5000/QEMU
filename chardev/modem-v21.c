/*
 * V.21 binary FSK signal primitives.
 * SPDX-License-Identifier: MIT
 */
#include "qemu/osdep.h"
#include <math.h>
#include "chardev/modem-v21.h"

/* ITU-T V.21 (1988): space (0), mark (1), in Hz. */
static const unsigned v21_frequency[][2] = {
    [MODEM_V21_CHANNEL_1] = { 1180, 980 },
    [MODEM_V21_CHANNEL_2] = { 1850, 1650 },
};

static double v21_angle(unsigned phase)
{
    return 2.0 * M_PI * phase / MODEM_V21_SAMPLE_RATE;
}

void modem_v21_tx_init(ModemV21Tx *tx, ModemV21Channel channel)
{
    assert(channel == MODEM_V21_CHANNEL_1 || channel == MODEM_V21_CHANNEL_2);
    tx->channel = channel;
    tx->phase = 0;
}

void modem_v21_tx_bit(ModemV21Tx *tx, bool bit,
                      int16_t samples[MODEM_V21_SAMPLES_PER_BIT])
{
    unsigned frequency = v21_frequency[tx->channel][bit];

    for (unsigned i = 0; i < MODEM_V21_SAMPLES_PER_BIT; i++) {
        /* Fixed digital amplitude; not a calibrated telephone-line level. */
        samples[i] = (int16_t)lrint(12000.0 * sin(v21_angle(tx->phase)));
        tx->phase = (tx->phase + frequency) % MODEM_V21_SAMPLE_RATE;
    }
}

/* Fit a sinusoid of arbitrary phase to the short, nonorthogonal window. */
static double v21_tone_energy(unsigned frequency, const int16_t *samples)
{
    double ss = 0, cc = 0, sc = 0, xs = 0, xc = 0;

    for (unsigned i = 0; i < MODEM_V21_SAMPLES_PER_BIT; i++) {
        double angle = v21_angle(i * frequency);
        double s = sin(angle);
        double c = cos(angle);

        ss += s * s;
        cc += c * c;
        sc += s * c;
        xs += samples[i] * s;
        xc += samples[i] * c;
    }
    return (cc * xs * xs - 2 * sc * xs * xc + ss * xc * xc) /
           (ss * cc - sc * sc);
}

int modem_v21_rx_bit(ModemV21Channel channel,
                     const int16_t samples[MODEM_V21_SAMPLES_PER_BIT])
{
    double zero, one;

    assert(channel == MODEM_V21_CHANNEL_1 || channel == MODEM_V21_CHANNEL_2);
    zero = v21_tone_energy(v21_frequency[channel][0], samples);
    one = v21_tone_energy(v21_frequency[channel][1], samples);

    if (MAX(zero, one) <= 0 || fabs(zero - one) < 0.05 * MAX(zero, one)) {
        return -1;
    }
    return one > zero;
}
