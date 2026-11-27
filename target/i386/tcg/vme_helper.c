/*
 * TCG virtual interrupt flag helpers for VME and PVI.
 * SPDX-License-Identifier: LGPL-2.1-or-later
 */
#include "qemu/osdep.h"
#include "cpu.h"
#include "exec/helper-proto.h"
#include "exec/cputlb.h"
#include "helper-tcg.h"
#include "vme-flags.h"

/* The translator calls this only for the restricted CPL 3 CLI/STI path. */
void helper_vme_set_if(CPUX86State *env, int set)
{
    if (!vme_if_allowed(env->cr[4], env->eflags, set)) {
        raise_exception_err_ra(env, EXCP0D_GPF, 0, GETPC());
    }

    if (set) {
        env->eflags |= VIF_MASK;
    } else {
        env->eflags &= ~VIF_MASK;
    }
}

/* Check before any operand stack access, preserving fault priority. */
void helper_vme_check(CPUX86State *env)
{
    if (!(env->cr[4] & CR4_VME_MASK)) {
        raise_exception_err_ra(env, EXCP0D_GPF, 0, GETPC());
    }
}

target_ulong helper_vme_read_flags(CPUX86State *env)
{
    return vme_flags_image(helper_read_eflags(env));
}

void helper_vme_write_flags(CPUX86State *env, target_ulong image)
{
    uint32_t value;

    if (!vme_flags_restore(env->eflags, image, &value)) {
        raise_exception_err_ra(env, EXCP0D_GPF, 0, GETPC());
    }

    /* IF, IOPL, VIP and VM are unaffected. CC and DF are loaded normally. */
    cpu_load_eflags(env, value, TF_MASK | NT_MASK | VIF_MASK);
}
