/*
 * Virtual-8086 and protected-mode virtual interrupt flag policy.
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */
#ifndef X86_TCG_VME_FLAGS_H
#define X86_TCG_VME_FLAGS_H

/* Caller has already checked CPL > IOPL and CPL == 3. */
static inline bool vme_if_allowed(uint32_t cr4, uint32_t flags,
                                  bool set)
{
    uint32_t required = (flags & VM_MASK) ? CR4_VME_MASK : CR4_PVI_MASK;

    return (cr4 & required) && (!set || !(flags & VIP_MASK));
}

static inline uint32_t vme_flags_image(uint32_t flags)
{
    return ((flags & ~IF_MASK) | IOPL_MASK |
            ((flags & VIF_MASK) ? IF_MASK : 0)) & 0xffff;
}

static inline bool vme_flags_restore(uint32_t flags, uint32_t image,
                                     uint32_t *value)
{
    if ((image & TF_MASK) || ((flags & VIP_MASK) && (image & IF_MASK))) {
        return false;
    }
    *value = (image & 0xffff) | ((image & IF_MASK) ? VIF_MASK : 0);
    return true;
}

#endif
