/*
 * QEMU TriMedia CPU support
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

static void trimedia_cpu_set_pc(CPUState *cs, vaddr value)
{
    TrimediaCPU *cpu = TRIMEDIA_CPU(cs);

    cpu->env.pc = value;
}

static vaddr trimedia_cpu_get_pc(CPUState *cs)
{
    TrimediaCPU *cpu = TRIMEDIA_CPU(cs);

    return cpu->env.pc;
}

static TCGTBCPUState trimedia_get_tb_cpu_state(CPUState *cs)
{
    CPUTrimediaState *env = cpu_env(cs);

    return (TCGTBCPUState){ .pc = env->pc };
}

static void trimedia_cpu_synchronize_from_tb(CPUState *cs,
                                             const TranslationBlock *tb)
{
    TrimediaCPU *cpu = TRIMEDIA_CPU(cs);

    cpu->env.pc = tb->pc;
}

static void trimedia_restore_state_to_opc(CPUState *cs,
                                          const TranslationBlock *tb,
                                          const uint64_t *data)
{
    TrimediaCPU *cpu = TRIMEDIA_CPU(cs);

    cpu->env.pc = data[0];
}

static bool trimedia_cpu_has_work(CPUState *cs)
{
    return cpu_test_interrupt(cs, CPU_INTERRUPT_HARD);
}

static int trimedia_cpu_mmu_index(CPUState *cs, bool ifetch)
{
    return 0;
}

static bool trimedia_cpu_tlb_fill(CPUState *cs, vaddr addr, int size,
                                  MMUAccessType access_type, int mmu_idx,
                                  bool probe, uintptr_t retaddr)
{
    vaddr page = addr & TARGET_PAGE_MASK;
    int prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;

    tlb_set_page(cs, page, page, prot, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static hwaddr trimedia_cpu_get_phys_addr_debug(CPUState *cs, vaddr addr)
{
    return addr;
}

static void trimedia_cpu_reset_hold(Object *obj, ResetType type)
{
    TrimediaCPU *cpu = TRIMEDIA_CPU(obj);
    TrimediaCPUClass *tcc = TRIMEDIA_CPU_GET_CLASS(obj);
    CPUTrimediaState *env = &cpu->env;

    if (tcc->parent_phases.hold) {
        tcc->parent_phases.hold(obj, type);
    }

    memset(env, 0, offsetof(CPUTrimediaState, end_reset_fields));

    /* TriMedia r0 and r1 are architectural constants 0 and 1. */
    env->gpr[0] = 0;
    env->gpr[1] = 1;
}

static ObjectClass *trimedia_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    char *typename;

    oc = object_class_by_name(cpu_model);
    if (oc != NULL && object_class_dynamic_cast(oc, TYPE_TRIMEDIA_CPU) != NULL) {
        return oc;
    }

    typename = g_strdup_printf(TRIMEDIA_CPU_TYPE_NAME("%s"), cpu_model);
    oc = object_class_by_name(typename);
    g_free(typename);

    return oc;
}

static void trimedia_cpu_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    TrimediaCPUClass *tcc = TRIMEDIA_CPU_GET_CLASS(dev);
    Error *local_err = NULL;

    cpu_exec_realizefn(cs, &local_err);
    if (local_err != NULL) {
        error_propagate(errp, local_err);
        return;
    }

    qemu_init_vcpu(cs);
    cpu_reset(cs);

    tcc->parent_realize(dev, errp);
}

static void trimedia_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUTrimediaState *env = cpu_env(cs);
    int i;

    qemu_fprintf(f, "pc=0x%08x pcsw=0x%08x\n", env->pc, env->pcsw);
    qemu_fprintf(f,
                 "dpc=0x%08x spc=0x%08x excvec=0x%08x "
                 "cccount=0x%016" PRIx64 "\n",
                 env->dpc, env->spc, env->excvec, env->cccount);
    for (i = 0; i < TRIMEDIA_NUM_GPRS; i += 4) {
        qemu_fprintf(f,
                     "r%-3d=0x%08x r%-3d=0x%08x r%-3d=0x%08x r%-3d=0x%08x\n",
                     i, env->gpr[i], i + 1, env->gpr[i + 1],
                     i + 2, env->gpr[i + 2], i + 3, env->gpr[i + 3]);
    }
}

#include "hw/core/sysemu-cpu-ops.h"

static const struct SysemuCPUOps trimedia_sysemu_ops = {
    .has_work = trimedia_cpu_has_work,
    .get_phys_addr_debug = trimedia_cpu_get_phys_addr_debug,
};

static const TCGCPUOps trimedia_tcg_ops = {
    /* VLIW packet ordering will need explicit modeling before MTTCG is safe. */
    .guest_default_memory_order = TCG_MO_ALL,
    .mttcg_supported = false,

    .initialize = trimedia_translate_init,
    .translate_code = trimedia_translate_code,
    .get_tb_cpu_state = trimedia_get_tb_cpu_state,
    .synchronize_from_tb = trimedia_cpu_synchronize_from_tb,
    .restore_state_to_opc = trimedia_restore_state_to_opc,
    .mmu_index = trimedia_cpu_mmu_index,
    .tlb_fill = trimedia_cpu_tlb_fill,
    .pointer_wrap = cpu_pointer_wrap_uint32,

    .cpu_exec_halt = trimedia_cpu_has_work,
    .cpu_exec_reset = cpu_reset,
};

static void trimedia_cpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    CPUClass *cc = CPU_CLASS(klass);
    TrimediaCPUClass *tcc = TRIMEDIA_CPU_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    device_class_set_parent_realize(dc, trimedia_cpu_realize,
                                    &tcc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, trimedia_cpu_reset_hold, NULL,
                                       &tcc->parent_phases);

    cc->class_by_name = trimedia_cpu_class_by_name;
    cc->dump_state = trimedia_cpu_dump_state;
    cc->set_pc = trimedia_cpu_set_pc;
    cc->get_pc = trimedia_cpu_get_pc;
    cc->sysemu_ops = &trimedia_sysemu_ops;
    cc->tcg_ops = &trimedia_tcg_ops;
}

static const TypeInfo trimedia_cpu_type_info = {
    .name = TYPE_TRIMEDIA_CPU,
    .parent = TYPE_CPU,
    .instance_size = sizeof(TrimediaCPU),
    .instance_align = __alignof(TrimediaCPU),
    .abstract = true,
    .class_size = sizeof(TrimediaCPUClass),
    .class_init = trimedia_cpu_class_init,
};

static const TypeInfo tm3260_cpu_type_info = {
    .name = TYPE_TM3260_CPU,
    .parent = TYPE_TRIMEDIA_CPU,
};

static void trimedia_cpu_register_types(void)
{
    type_register_static(&trimedia_cpu_type_info);
    type_register_static(&tm3260_cpu_type_info);
}

type_init(trimedia_cpu_register_types)
