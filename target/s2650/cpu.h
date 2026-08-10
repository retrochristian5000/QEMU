/*
 * Signetics 2650 CPU definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_S2650_CPU_H
#define QEMU_S2650_CPU_H

#include "cpu-qom.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"

#ifdef CONFIG_USER_ONLY
#error "Signetics 2650 does not support user mode emulation"
#endif

#define S2650_ADDRESS_MASK 0x7fff
#define S2650_NUM_GPRS 7
#define S2650_RETURN_STACK_DEPTH 8

/*
 * Register layout:
 *   gpr[0]      = R0 (shared accumulator)
 *   gpr[1..3]   = R1..R3, bank 0
 *   gpr[4..6]   = R1'..R3', bank 1
 *
 * The PSL register-select bit chooses which R1..R3 bank is active.  Keep both
 * banks explicit so the eventual decoder can implement register switching
 * without shuffling architectural state.
 */
typedef struct CPUArchState {
    uint32_t gpr[S2650_NUM_GPRS];       /* architectural values are 8-bit */
    uint32_t pc;                        /* architectural value is 15-bit */
    uint32_t psu;                       /* Program Status Upper, 8-bit */
    uint32_t psl;                       /* Program Status Lower, 8-bit */
    uint32_t ras[S2650_RETURN_STACK_DEPTH]; /* 15-bit return addresses */

    /* External single-bit Sense input; Flag output is represented in PSU. */
    uint32_t sense;

    /* Fields up to this point are cleared by CPU reset. */
    struct {} end_reset_fields;
} CPUS2650State;

struct ArchCPU {
    CPUState parent_obj;
    CPUS2650State env;
};

struct S2650CPUClass {
    CPUClass parent_class;

    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

#define CPU_RESOLVING_TYPE TYPE_S2650_CPU

void s2650_translate_init(void);
void s2650_translate_code(CPUState *cs, TranslationBlock *tb,
                          int *max_insns, vaddr pc, void *host_pc);

#endif /* QEMU_S2650_CPU_H */
