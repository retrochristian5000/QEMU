/*
 * QEMU Toshiba MeP CPU support
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

static void mep_cpu_set_pc(CPUState *cs, vaddr value)
{
    MEPCPU *cpu = MEP_CPU(cs);

    cpu->env.pc = value;
}

static vaddr mep_cpu_get_pc(CPUState *cs)
{
    MEPCPU *cpu = MEP_CPU(cs);

    return cpu->env.pc;
}

static TCGTBCPUState mep_get_tb_cpu_state(CPUState *cs)
{
    CPUMEPState *env = cpu_env(cs);

    return (TCGTBCPUState){ .pc = env->pc };
}

static void mep_cpu_synchronize_from_tb(CPUState *cs,
                                        const TranslationBlock *tb)
{
    MEPCPU *cpu = MEP_CPU(cs);

    cpu->env.pc = tb->pc;
}

static void mep_restore_state_to_opc(CPUState *cs,
                                     const TranslationBlock *tb,
                                     const uint64_t *data)
{
    MEPCPU *cpu = MEP_CPU(cs);

    cpu->env.pc = data[0];
}

static bool mep_cpu_has_work(CPUState *cs)
{
    return cpu_test_interrupt(cs, CPU_INTERRUPT_HARD);
}

static int mep_cpu_mmu_index(CPUState *cs, bool ifetch)
{
    return 0;
}

static bool mep_cpu_tlb_fill(CPUState *cs, vaddr addr, int size,
                             MMUAccessType access_type, int mmu_idx,
                             bool probe, uintptr_t retaddr)
{
    vaddr page = addr & TARGET_PAGE_MASK;
    int prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;

    tlb_set_page(cs, page, page, prot, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static hwaddr mep_cpu_get_phys_addr_debug(CPUState *cs, vaddr addr)
{
    return addr;
}

static void mep_cpu_reset_hold(Object *obj, ResetType type)
{
    MEPCPU *cpu = MEP_CPU(obj);
    MEPCPUClass *mcc = MEP_CPU_GET_CLASS(obj);
    CPUMEPState *env = &cpu->env;

    if (mcc->parent_phases.hold) {
        mcc->parent_phases.hold(obj, type);
    }

    memset(env, 0, offsetof(CPUMEPState, end_reset_fields));
    env->pc = 0;
}

static ObjectClass *mep_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    char *typename;

    oc = object_class_by_name(cpu_model);
    if (oc != NULL && object_class_dynamic_cast(oc, TYPE_MEP_CPU) != NULL) {
        return oc;
    }

    typename = g_strdup_printf(MEP_CPU_TYPE_NAME("%s"), cpu_model);
    oc = object_class_by_name(typename);
    g_free(typename);

    return oc;
}

static void mep_cpu_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    MEPCPUClass *mcc = MEP_CPU_GET_CLASS(dev);
    Error *local_err = NULL;

    cpu_exec_realizefn(cs, &local_err);
    if (local_err != NULL) {
        error_propagate(errp, local_err);
        return;
    }

    qemu_init_vcpu(cs);
    cpu_reset(cs);

    mcc->parent_realize(dev, errp);
}

static void mep_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUMEPState *env = cpu_env(cs);
    unsigned int i;

    qemu_fprintf(f, "pc=%08x\n", env->pc);
    for (i = 0; i < MEP_NUM_GPRS; i += 4) {
        qemu_fprintf(f,
                     "r%-2u=%08x r%-2u=%08x r%-2u=%08x r%-2u=%08x\n",
                     i, env->gpr[i], i + 1, env->gpr[i + 1],
                     i + 2, env->gpr[i + 2], i + 3, env->gpr[i + 3]);
    }
}

#include "hw/core/sysemu-cpu-ops.h"

static const struct SysemuCPUOps mep_sysemu_ops = {
    .has_work = mep_cpu_has_work,
    .get_phys_addr_debug = mep_cpu_get_phys_addr_debug,
};

static const TCGCPUOps mep_tcg_ops = {
    .guest_default_memory_order = TCG_MO_ALL,
    .mttcg_supported = false,

    .initialize = mep_translate_init,
    .translate_code = mep_translate_code,
    .get_tb_cpu_state = mep_get_tb_cpu_state,
    .synchronize_from_tb = mep_cpu_synchronize_from_tb,
    .restore_state_to_opc = mep_restore_state_to_opc,
    .mmu_index = mep_cpu_mmu_index,
    .tlb_fill = mep_cpu_tlb_fill,
    .pointer_wrap = cpu_pointer_wrap_uint32,

    .cpu_exec_halt = mep_cpu_has_work,
    .cpu_exec_reset = cpu_reset,
};

static void mep_cpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    CPUClass *cc = CPU_CLASS(klass);
    MEPCPUClass *mcc = MEP_CPU_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    device_class_set_parent_realize(dc, mep_cpu_realize,
                                    &mcc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, mep_cpu_reset_hold, NULL,
                                       &mcc->parent_phases);

    cc->class_by_name = mep_cpu_class_by_name;
    cc->dump_state = mep_cpu_dump_state;
    cc->set_pc = mep_cpu_set_pc;
    cc->get_pc = mep_cpu_get_pc;
    cc->sysemu_ops = &mep_sysemu_ops;
    cc->tcg_ops = &mep_tcg_ops;
}

static const TypeInfo mep_cpu_type_info = {
    .name = TYPE_MEP_CPU,
    .parent = TYPE_CPU,
    .instance_size = sizeof(MEPCPU),
    .instance_align = __alignof(MEPCPU),
    .abstract = true,
    .class_size = sizeof(MEPCPUClass),
    .class_init = mep_cpu_class_init,
};

static const TypeInfo mep_default_cpu_type_info = {
    .name = TYPE_MEP_DEFAULT_CPU,
    .parent = TYPE_MEP_CPU,
};

static void mep_cpu_register_types(void)
{
    type_register_static(&mep_cpu_type_info);
    type_register_static(&mep_default_cpu_type_info);
}

type_init(mep_cpu_register_types)
