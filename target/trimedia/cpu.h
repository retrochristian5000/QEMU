/*
 * QEMU TriMedia CPU definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_TRIMEDIA_CPU_H
#define QEMU_TRIMEDIA_CPU_H

#include "cpu-qom.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"

#ifdef CONFIG_USER_ONLY
#error "TriMedia does not support user mode emulation yet"
#endif

#define TRIMEDIA_NUM_GPRS 128

typedef struct CPUArchState {
    uint32_t gpr[TRIMEDIA_NUM_GPRS];
    uint32_t pc;
    uint32_t pcsw;
    uint32_t dpc;
    uint32_t spc;
    uint32_t excvec;
    uint64_t cccount;

    /* Fields up to this point are cleared by CPU reset. */
    struct {} end_reset_fields;
} CPUTrimediaState;

struct ArchCPU {
    CPUState parent_obj;
    CPUTrimediaState env;
};

struct TrimediaCPUClass {
    CPUClass parent_class;

    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

#define CPU_RESOLVING_TYPE TYPE_TRIMEDIA_CPU

void trimedia_translate_init(void);
void trimedia_translate_code(CPUState *cs, TranslationBlock *tb,
                             int *max_insns, vaddr pc, void *host_pc);

#endif
