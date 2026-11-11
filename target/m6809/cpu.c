/*
 * QEMU Motorola MC6809 and MC6809E CPU skeleton
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "qemu/qemu-print.h"
#include "qapi/error.h"
#include "cpu.h"
#include "exec/cputlb.h"
#include "exec/page-protection.h"
#include "exec/target_page.h"
#include "exec/translation-block.h"
#include "accel/tcg/cpu-ops.h"
#include "system/address-spaces.h"
#include "system/memory.h"

static void m6809_cpu_set_pc(CPUState *cs, vaddr value)
{
    M6809CPU *cpu = M6809_CPU(cs);

    cpu->env.pc = value & M6809_ADDRESS_MASK;
}

static vaddr m6809_cpu_get_pc(CPUState *cs)
{
    M6809CPU *cpu = M6809_CPU(cs);

    return cpu->env.pc & M6809_ADDRESS_MASK;
}

static TCGTBCPUState m6809_get_tb_cpu_state(CPUState *cs)
{
    CPUM6809State *env = cpu_env(cs);

    return (TCGTBCPUState){ .pc = env->pc & M6809_ADDRESS_MASK };
}

static void m6809_cpu_synchronize_from_tb(CPUState *cs,
                                        const TranslationBlock *tb)
{
    M6809CPU *cpu = M6809_CPU(cs);

    cpu->env.pc = tb->pc & M6809_ADDRESS_MASK;
}

static void m6809_restore_state_to_opc(CPUState *cs,
                                     const TranslationBlock *tb,
                                     const uint64_t *data)
{
    M6809CPU *cpu = M6809_CPU(cs);

    cpu->env.pc = data[0] & M6809_ADDRESS_MASK;
}

static bool m6809_cpu_has_work(CPUState *cs)
{
    CPUM6809State *env = cpu_env(cs);

    return cpu_test_interrupt(cs, CPU_INTERRUPT_NMI) ||
           (!(env->cc & M6809_CC_F) &&
            cpu_test_interrupt(cs, CPU_INTERRUPT_FIR)) ||
           (!(env->cc & M6809_CC_I) &&
            cpu_test_interrupt(cs, CPU_INTERRUPT_HARD));
}

static int m6809_cpu_mmu_index(CPUState *cs, bool ifetch)
{
    return 0;
}

static bool m6809_cpu_tlb_fill(CPUState *cs, vaddr addr, int size,
                             MMUAccessType access_type, int mmu_idx,
                             bool probe, uintptr_t retaddr)
{
    vaddr vpage = addr & TARGET_PAGE_MASK;
    hwaddr ppage = (addr & M6809_ADDRESS_MASK) & TARGET_PAGE_MASK;
    int prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;

    tlb_set_page(cs, vpage, ppage, prot, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static hwaddr m6809_cpu_get_phys_addr_debug(CPUState *cs, vaddr addr)
{
    return addr & M6809_ADDRESS_MASK;
}

static void m6809_cpu_reset_hold(Object *obj, ResetType type)
{
    CPUState *cs = CPU(obj);
    M6809CPU *cpu = M6809_CPU(obj);
    M6809CPUClass *mcc = M6809_CPU_GET_CLASS(obj);
    CPUM6809State *env = &cpu->env;

    if (mcc->parent_phases.hold) {
        mcc->parent_phases.hold(obj, type);
    }

    /*
     * MC6809 RESTART (M6809PM/AD): DP=00, F=I=1, PC=[FFFE:FFFF].
     * The reset states of A, B, X, Y, U, S and other CC bits are
     * unspecified; do not manufacture values for them.
     * The future machine must map its ROM before system reset.
     */
    env->dp = 0;
    env->cc |= M6809_CC_I | M6809_CC_F;
    env->pc = address_space_lduw_be(&address_space_memory, M6809_RESET_VECTOR,
                                    MEMTXATTRS_UNSPECIFIED, NULL);
    cs->halted = 0;
    cs->exception_index = -1;
}

static ObjectClass *m6809_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    char *typename;

    oc = object_class_by_name(cpu_model);
    if (oc != NULL && object_class_dynamic_cast(oc, TYPE_M6809_CPU) != NULL) {
        return oc;
    }

    typename = g_strdup_printf(M6809_CPU_TYPE_NAME("%s"), cpu_model);
    oc = object_class_by_name(typename);
    g_free(typename);

    return oc;
}

static void m6809_cpu_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    M6809CPUClass *zcc = M6809_CPU_GET_CLASS(dev);
    Error *local_err = NULL;

    cpu_exec_realizefn(cs, &local_err);
    if (local_err != NULL) {
        error_propagate(errp, local_err);
        return;
    }

    qemu_init_vcpu(cs);
    cpu_reset(cs);

    zcc->parent_realize(dev, errp);
}

static void m6809_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUM6809State *env = cpu_env(cs);

    qemu_fprintf(f, "PC=%04x S=%04x U=%04x X=%04x Y=%04x\n",
                 env->pc & 0xffff, env->s & 0xffff, env->u & 0xffff,
                 env->x & 0xffff, env->y & 0xffff);
    qemu_fprintf(f, "A=%02x B=%02x D=%04x DP=%02x CC=%02x\n",
                 env->a & 0xff, env->b & 0xff,
                 ((env->a & 0xff) << 8) | (env->b & 0xff),
                 env->dp & 0xff, env->cc & 0xff);
}

#include "hw/core/sysemu-cpu-ops.h"

static const struct SysemuCPUOps m6809_sysemu_ops = {
    .has_work = m6809_cpu_has_work,
    .get_phys_addr_debug = m6809_cpu_get_phys_addr_debug,
};

static const TCGCPUOps m6809_tcg_ops = {
    .guest_default_memory_order = TCG_MO_ALL,
    .mttcg_supported = false,

    .initialize = m6809_translate_init,
    .translate_code = m6809_translate_code,
    .get_tb_cpu_state = m6809_get_tb_cpu_state,
    .synchronize_from_tb = m6809_cpu_synchronize_from_tb,
    .restore_state_to_opc = m6809_restore_state_to_opc,
    .mmu_index = m6809_cpu_mmu_index,
    .tlb_fill = m6809_cpu_tlb_fill,
    .pointer_wrap = cpu_pointer_wrap_uint32,

    .cpu_exec_halt = m6809_cpu_has_work,
    .cpu_exec_reset = cpu_reset,
};

static void m6809_cpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    CPUClass *cc = CPU_CLASS(klass);
    M6809CPUClass *zcc = M6809_CPU_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    device_class_set_parent_realize(dc, m6809_cpu_realize,
                                    &zcc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, m6809_cpu_reset_hold, NULL,
                                       &zcc->parent_phases);

    cc->class_by_name = m6809_cpu_class_by_name;
    cc->dump_state = m6809_cpu_dump_state;
    cc->set_pc = m6809_cpu_set_pc;
    cc->get_pc = m6809_cpu_get_pc;
    cc->sysemu_ops = &m6809_sysemu_ops;
    cc->tcg_ops = &m6809_tcg_ops;
}

static const TypeInfo m6809_cpu_type_info[] = {
    {
        .name = TYPE_M6809_CPU,
        .parent = TYPE_CPU,
        .instance_size = sizeof(M6809CPU),
        .instance_align = __alignof(M6809CPU),
        .abstract = true,
        .class_size = sizeof(M6809CPUClass),
        .class_init = m6809_cpu_class_init,
    },
    { .name = TYPE_M6809_6809_CPU, .parent = TYPE_M6809_CPU },
    { .name = TYPE_M6809_6809E_CPU, .parent = TYPE_M6809_CPU },
};

DEFINE_TYPES(m6809_cpu_type_info)
