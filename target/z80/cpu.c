/*
 * QEMU Zilog Z80 CPU support
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

static void z80_cpu_set_pc(CPUState *cs, vaddr value)
{
    Z80CPU *cpu = Z80_CPU(cs);

    cpu->env.pc = value & Z80_ADDRESS_MASK;
}

static vaddr z80_cpu_get_pc(CPUState *cs)
{
    Z80CPU *cpu = Z80_CPU(cs);

    return cpu->env.pc & Z80_ADDRESS_MASK;
}

static TCGTBCPUState z80_get_tb_cpu_state(CPUState *cs)
{
    CPUZ80State *env = cpu_env(cs);

    return (TCGTBCPUState){ .pc = env->pc & Z80_ADDRESS_MASK };
}

static void z80_cpu_synchronize_from_tb(CPUState *cs,
                                        const TranslationBlock *tb)
{
    Z80CPU *cpu = Z80_CPU(cs);

    cpu->env.pc = tb->pc & Z80_ADDRESS_MASK;
}

static void z80_restore_state_to_opc(CPUState *cs,
                                     const TranslationBlock *tb,
                                     const uint64_t *data)
{
    Z80CPU *cpu = Z80_CPU(cs);

    cpu->env.pc = data[0] & Z80_ADDRESS_MASK;
}

static bool z80_cpu_has_work(CPUState *cs)
{
    CPUZ80State *env = cpu_env(cs);

    if (cpu_test_interrupt(cs, CPU_INTERRUPT_NMI)) {
        return true;
    }

    return env->iff1 && cpu_test_interrupt(cs, CPU_INTERRUPT_HARD);
}

static int z80_cpu_mmu_index(CPUState *cs, bool ifetch)
{
    return 0;
}

static bool z80_cpu_tlb_fill(CPUState *cs, vaddr addr, int size,
                             MMUAccessType access_type, int mmu_idx,
                             bool probe, uintptr_t retaddr)
{
    vaddr vpage = addr & TARGET_PAGE_MASK;
    hwaddr ppage = (addr & Z80_ADDRESS_MASK) & TARGET_PAGE_MASK;
    int prot = PAGE_READ | PAGE_WRITE | PAGE_EXEC;

    tlb_set_page(cs, vpage, ppage, prot, mmu_idx, TARGET_PAGE_SIZE);
    return true;
}

static hwaddr z80_cpu_get_phys_addr_debug(CPUState *cs, vaddr addr)
{
    return addr & Z80_ADDRESS_MASK;
}

static void z80_cpu_reset_hold(Object *obj, ResetType type)
{
    CPUState *cs = CPU(obj);
    Z80CPU *cpu = Z80_CPU(obj);
    Z80CPUClass *zcc = Z80_CPU_GET_CLASS(obj);
    CPUZ80State *env = &cpu->env;

    if (zcc->parent_phases.hold) {
        zcc->parent_phases.hold(obj, type);
    }

    /*
     * Zilog documents RESET as clearing PC, I, R, IFF1 and IFF2 and
     * selecting interrupt mode 0. Do not manufacture reset values for
     * registers whose reset state is not specified by the CPU manual.
     */
    env->pc = 0;
    env->i = 0;
    env->r = 0;
    env->iff1 = 0;
    env->iff2 = 0;
    env->im = 0;

    cs->halted = 0;
    cs->exception_index = -1;
}

static ObjectClass *z80_cpu_class_by_name(const char *cpu_model)
{
    ObjectClass *oc;
    char *typename;

    oc = object_class_by_name(cpu_model);
    if (oc != NULL && object_class_dynamic_cast(oc, TYPE_Z80_CPU) != NULL) {
        return oc;
    }

    typename = g_strdup_printf(Z80_CPU_TYPE_NAME("%s"), cpu_model);
    oc = object_class_by_name(typename);
    g_free(typename);

    return oc;
}

static void z80_cpu_realize(DeviceState *dev, Error **errp)
{
    CPUState *cs = CPU(dev);
    Z80CPUClass *zcc = Z80_CPU_GET_CLASS(dev);
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

static void z80_cpu_dump_state(CPUState *cs, FILE *f, int flags)
{
    CPUZ80State *env = cpu_env(cs);

    qemu_fprintf(f,
                 "PC=%04x SP=%04x IX=%04x IY=%04x I=%02x R=%02x "
                 "IFF=%u/%u IM=%u\n",
                 env->pc & 0xffff, env->sp & 0xffff,
                 env->ix & 0xffff, env->iy & 0xffff,
                 env->i & 0xff, env->r & 0xff,
                 env->iff1 & 1, env->iff2 & 1, env->im & 3);
    qemu_fprintf(f, "AF=%04x BC=%04x DE=%04x HL=%04x\n",
                 env->af & 0xffff, env->bc & 0xffff,
                 env->de & 0xffff, env->hl & 0xffff);
    qemu_fprintf(f, "AF'=%04x BC'=%04x DE'=%04x HL'=%04x\n",
                 env->af2 & 0xffff, env->bc2 & 0xffff,
                 env->de2 & 0xffff, env->hl2 & 0xffff);
}

#include "hw/core/sysemu-cpu-ops.h"

static const struct SysemuCPUOps z80_sysemu_ops = {
    .has_work = z80_cpu_has_work,
    .get_phys_addr_debug = z80_cpu_get_phys_addr_debug,
};

static const TCGCPUOps z80_tcg_ops = {
    .guest_default_memory_order = TCG_MO_ALL,
    .mttcg_supported = false,

    .initialize = z80_translate_init,
    .translate_code = z80_translate_code,
    .get_tb_cpu_state = z80_get_tb_cpu_state,
    .synchronize_from_tb = z80_cpu_synchronize_from_tb,
    .restore_state_to_opc = z80_restore_state_to_opc,
    .mmu_index = z80_cpu_mmu_index,
    .tlb_fill = z80_cpu_tlb_fill,
    .pointer_wrap = cpu_pointer_wrap_uint32,

    .cpu_exec_halt = z80_cpu_has_work,
    .cpu_exec_reset = cpu_reset,
};

static void z80_cpu_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);
    CPUClass *cc = CPU_CLASS(klass);
    Z80CPUClass *zcc = Z80_CPU_CLASS(klass);
    ResettableClass *rc = RESETTABLE_CLASS(klass);

    device_class_set_parent_realize(dc, z80_cpu_realize,
                                    &zcc->parent_realize);
    resettable_class_set_parent_phases(rc, NULL, z80_cpu_reset_hold, NULL,
                                       &zcc->parent_phases);

    cc->class_by_name = z80_cpu_class_by_name;
    cc->dump_state = z80_cpu_dump_state;
    cc->set_pc = z80_cpu_set_pc;
    cc->get_pc = z80_cpu_get_pc;
    cc->sysemu_ops = &z80_sysemu_ops;
    cc->tcg_ops = &z80_tcg_ops;
}

static const TypeInfo z80_cpu_type_info[] = {
    {
        .name = TYPE_Z80_CPU,
        .parent = TYPE_CPU,
        .instance_size = sizeof(Z80CPU),
        .instance_align = __alignof(Z80CPU),
        .abstract = true,
        .class_size = sizeof(Z80CPUClass),
        .class_init = z80_cpu_class_init,
    },
    {
        .name = TYPE_Z80_Z80_CPU,
        .parent = TYPE_Z80_CPU,
    },
    {
        .name = TYPE_Z80_Z80A_CPU,
        .parent = TYPE_Z80_CPU,
    },
};

DEFINE_TYPES(z80_cpu_type_info)
