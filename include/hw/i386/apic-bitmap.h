/* SPDX-License-Identifier: LGPL-2.1-or-later */
#ifndef HW_I386_APIC_BITMAP_H
#define HW_I386_APIC_BITMAP_H

#include <stdint.h>

/* APIC register words and destination bitmaps use unsigned 32-bit masks. */
static inline uint32_t apic_bit_mask(int index)
{
    return UINT32_C(1) << (index & 31);
}

static inline void apic_set_bit(uint32_t *tab, int index)
{
    tab[index >> 5] |= apic_bit_mask(index);
}

static inline int apic_get_bit(const uint32_t *tab, int index)
{
    return !!(tab[index >> 5] & apic_bit_mask(index));
}

static inline void apic_reset_bit(uint32_t *tab, int index)
{
    tab[index >> 5] &= ~apic_bit_mask(index);
}

/* Fixed interrupts are subject to the local APIC priority classes. */
static inline int apic_priority_blocked(int vector, uint8_t priority)
{
    return priority && (vector & 0xf0) <= (priority & 0xf0);
}

#endif
