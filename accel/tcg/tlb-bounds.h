/*
 * softmmu size bounds
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */

#ifndef ACCEL_TCG_TLB_BOUNDS_H
#define ACCEL_TCG_TLB_BOUNDS_H

#define CPU_TLB_DYN_MIN_BITS 6
#define CPU_TLB_DYN_MAX_BITS (32 - TARGET_PAGE_BITS)
#define CPU_TLB_DYN_DEFAULT_BITS 8

/* Account for the state transition of one direct-mapped TLB slot. */
static inline void tlb_usage_update(size_t *used, bool was_used, bool is_used)
{
    if (was_used == is_used) {
        return;
    }
    if (is_used) {
        ++*used;
    } else {
        assert(*used > 0);
        --*used;
    }
}

#endif /* ACCEL_TCG_TLB_BOUNDS_H */
