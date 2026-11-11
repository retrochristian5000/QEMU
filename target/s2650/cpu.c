/*
 * QEMU Signetics 2650 CPU support
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

static void s2650_cpu_set_pc(CPUState *cs, vaddr value)
{
    S2650CPU *cpu = S2650_CPU(cs);

    cpu->env.pc = value & S2650_ADDRESS_MASK;
}

static vaddr s2650_cpu_get_pc(CPUState *cs)
{
    S2650CPU *cpu = S2650_CPU(cs);

    return cpu->env.pc & S2650_ADDRESS_MASK;
}

static TCGTBCPUState s2650_get_tb_cpu_state(CPUState *cs)
{
    CPUS2650State *env = cpu_env(cs);

    return (TCGTBCPUState){ .pc = env->pc & S2650_ADDRESS_MASK };
}

static void s2650_cpu_synchronize_from_tb(CPUState *cs,
                                          const TranslationBlock *tb)
{
    S2650CPU *cpu = S2650_CPU(cs);

    cpu->env.pc = tb->pc & S2650_ADDRESS_MASK;
}

static void s2650_restore_state_to_opc(CPUState *cs,
                                       const TranslationBlock *tb,
                                       const uint64_t *data)
{
    S2650CPU *cpu = S2650_CPU(cs);

    cpu->env.pc = data[0] & S2650_ADDRESS_MASK;
}

static bool s2650_cpu_has_work(CPUState *cs)
{
    return cpu_test_interrupt(cs, CPU_INTERRUPT_HARD);
}

static int s2650_cpu_mmu_index(CPUState *cs, bool ifetch)
{
    return 0;
}

static bool s2650_cpu_tlb_fill(CPUState *cs, vaddr addr, int size,
                               MMUAccessType access_type, int mmu_idx,
                               bool probe, uintptr_t retaddr)
{
    vaddr vpage = addr & TARGET_PAGE_MASK;
    hwaddr ppage = (addr & S2650_ADDRESS_MASK) & TARGET_PAGE_MASK;
    int prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;

    tlb_set_page(cs, vpage, ppage, prot, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static hwaddr s2650_cpu_get_phys_addr_debug(CPUState *cs, vaddr addr)
{
    return addr & S2650_ADDRESS_MASK;
}

static void s2650_cpu_reset_hold(Object *obj, ResetType type)
{
    S2650CPU *cpu = S2650_CPU(obj);
    S2650CPUClass *scc = S2650_CPU_GET_CLASS(obj);
    CPUS2650State *env = &cpu->env;

    if (scc->parent_phases.hold) {
        scc->parent_phases.hold(obj, type);
    }

    memset(env, 0, offsetof(CPUS2650State, end_reset_fields));

    /* RESET clears the page latches, so execution begins in page zero. */
    env->pc = 0;
}

static ObjectClass *s2650_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    char *typename;

    oc = object_class_by_name(cpu_model);
    if (oc != NULL && object_class_dynamic_cast(oc, TYPE_S2650_CPU) != NULL) {
        return oc;
    }

    typename = g_strdup_printf(S2650_CPU_TYPE_NAME("%s"), cpu_model);
    oc = object_class_by_name(typename);
    g_free(typename);

    return oc;
}

static void s2650_cpu_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    S2650CPUClass *scc = S2650_CPU_GET_CLASS(dev);
    Error *local_err = NULL;

    cpu_exec_realizefn(cs, &local_err);
    if (local_err != NULL) {
        error_propagate(errp, local_err);
        return;
    }

    qemu_init_vcpu(cs);
    cpu_reset(cs);

    scc->parent_realize(dev, errp);
}

static void s2650_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUS2650State *env = cpu_env(cs);

    qemu_fprintf(f, "pc=%04x psu=%02x psl=%02x sense=%u\n",
                 env->pc & S2650_ADDRESS_MASK,
                 env->psu & 0xff, env->psl & 0xff, env->sense & 1);
    qemu_fprintf(f, "r0=%02x r1=%02x r2=%02x r3=%02x\n",
                 env->gpr[0] & 0xff, env->gpr[1] & 0xff,
                 env->gpr[2] & 0xff, env->gpr[3] & 0xff);
    qemu_fprintf(f, "r1'=%02x r2'=%02x r3'=%02x\n",
                 env->gpr[4] & 0xff, env->gpr[5] & 0xff,
                 env->gpr[6] & 0xff);
}

#include "hw/core/sysemu-cpu-ops.h"

static const struct SysemuCPUOps s2650_sysemu_ops = {
    .has_work = s2650_cpu_has_work,
    .get_phys_addr_debug = s2650_cpu_get_phys_addr_debug,
};

static const TCGCPUOps s2650_tcg_ops = {
    .guest_default_memory_order = TCG_MO_ALL,
    .mttcg_supported = false,

    .initialize = s2650_translate_init,
    .translate_code = s2650_translate_code,
    .get_tb_cpu_state = s2650_get_tb_cpu_state,
    .synchronize_from_tb = s2650_cpu_synchronize_from_tb,
    .restore_state_to_opc = s2650_restore_state_to_opc,
    .mmu_index = s2650_cpu_mmu_index,
    .tlb_fill = s2650_cpu_tlb_fill,
    .pointer_wrap = cpu_pointer_wrap_uint32,

    .cpu_exec_halt = s2650_cpu_has_work,
    .cpu_exec_reset = cpu_reset,
};

static void s2650_cpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    CPUClass *cc = CPU_CLASS(klass);
    S2650CPUClass *scc = S2650_CPU_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    device_class_set_parent_realize(dc, s2650_cpu_realize,
                                    &scc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, s2650_cpu_reset_hold, NULL,
                                       &scc->parent_phases);

    cc->class_by_name = s2650_cpu_class_by_name;
    cc->dump_state = s2650_cpu_dump_state;
    cc->set_pc = s2650_cpu_set_pc;
    cc->get_pc = s2650_cpu_get_pc;
    cc->sysemu_ops = &s2650_sysemu_ops;
    cc->tcg_ops = &s2650_tcg_ops;
}

static const TypeInfo s2650_cpu_type_info = {
    .name = TYPE_S2650_CPU,
    .parent = TYPE_CPU,
    .instance_size = sizeof(S2650CPU),
    .instance_align = __alignof(S2650CPU),
    .abstract = true,
    .class_size = sizeof(S2650CPUClass),
    .class_init = s2650_cpu_class_init,
};

static const TypeInfo s2650_2650_cpu_type_info = {
    .name = TYPE_S2650_2650_CPU,
    .parent = TYPE_S2650_CPU,
};

static const TypeInfo s2650_2650a_cpu_type_info = {
    .name = TYPE_S2650_2650A_CPU,
    .parent = TYPE_S2650_CPU,
};

static void s2650_cpu_register_types(void)
{
    type_register_static(&s2650_cpu_type_info);
    type_register_static(&s2650_2650_cpu_type_info);
    type_register_static(&s2650_2650a_cpu_type_info);
}

type_init(s2650_cpu_register_types)
