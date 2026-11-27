/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_AUDIO_PCSPK_SIGNAL_H
#define HW_AUDIO_PCSPK_SIGNAL_H

#include <stdint.h>

/* Approximate normal ISA refresh cadence, without scheduling extra timers. */
static inline uint8_t pcspk_refresh_bit(uint64_t ns)
{
    return ((ns / 15000) & 1) << 4;
}

/*
 * Phase is in PIT ticks scaled by the sample rate. Keep fractional samples
 * between callbacks rather than replaying a rounded whole-period buffer.
 * The caller supplies a valid divisor and a bounded sample rate.
 */
static inline uint8_t pcspk_square_sample(uint32_t phase, uint32_t count,
                                          uint32_t rate)
{
    return phase < ((count + 1) / 2) * rate ? 160 : 96;
}

static inline uint32_t pcspk_advance_phase(uint32_t phase, uint32_t period,
                                          uint32_t clocks, uint32_t samples)
{
    return (phase + (uint64_t)clocks * samples) % period;
}

#endif
