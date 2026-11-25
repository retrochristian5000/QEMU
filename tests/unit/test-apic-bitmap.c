/* SPDX-License-Identifier: GPL-2.0-or-later */
#undef NDEBUG
#include <assert.h>
#include "hw/i386/apic-bitmap.h"

int main(void)
{
    uint32_t tab[16] = { 0 };

    /* Include destination IDs above the 256-vector register range. */
    for (int i = 0; i < 512; i++) {
        apic_set_bit(tab, i);
        for (int j = 0; j < 512; j++) {
            assert(apic_get_bit(tab, j) == (i == j));
        }
        apic_reset_bit(tab, i);
        assert(!apic_get_bit(tab, i));
    }
    for (int i = 0; i < 512; i++) {
        apic_set_bit(tab, i);
    }
    for (int i = 0; i < 16; i++) {
        assert(tab[i] == UINT32_MAX);
    }
    for (int i = 0; i < 512; i++) {
        apic_reset_bit(tab, i);
        for (int j = 0; j < 512; j++) {
            assert(apic_get_bit(tab, j) == (j > i));
        }
    }

    /* Compare the early TPR rejection against the original PPR policy. */
    for (int vector = 0; vector < 256; vector++) {
        for (int tpr = 0; tpr < 256; tpr++) {
            for (int isr_class = 0; isr_class < 16; isr_class++) {
                int ppr = tpr / 16 >= isr_class ? tpr : isr_class * 16;
                int old = ppr && (vector & 0xf0) <= (ppr & 0xf0);
                int now = apic_priority_blocked(vector, tpr) ||
                          apic_priority_blocked(vector, ppr);

                assert(old == now);
            }
        }
    }
    return 0;
}
