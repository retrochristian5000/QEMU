/*
 * Toshiba MeP CPU definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_MEP_CPU_H
#define QEMU_MEP_CPU_H

#include "cpu-qom.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"

#ifdef CONFIG_USER_ONLY
#error "Toshiba MeP does not support user mode emulation"
#endif

#define MEP_NUM_GPRS 16
#define MEP_NUM_CSRS 32

typedef struct CPUArchState {
    uint32_t gpr[MEP_NUM_GPRS];
    uint32_t csr[MEP_NUM_CSRS];
    uint32_t pc;

    /* Fields up to this point are cleared by CPU reset. */
    struct {} end_reset_fields;
} CPUMEPState;

struct ArchCPU {
    CPUState parent_obj;
    CPUMEPState env;
};

struct MEPCPUClass {
    CPUClass parent_class;

    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

#define CPU_RESOLVING_TYPE TYPE_MEP_CPU

void mep_translate_init(void);
void mep_translate_code(CPUState *cs, TranslationBlock *tb,
                        int *max_insns, vaddr pc, void *host_pc);

#endif /* QEMU_MEP_CPU_H */
