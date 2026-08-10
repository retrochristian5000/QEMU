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

/* PSU bit assignments for the 2650/2650A generation. */
#define S2650_PSU_SP_MASK 0x07
#define S2650_PSU_II      0x20
#define S2650_PSU_FLAG    0x40
#define S2650_PSU_SENSE   0x80

/* PSL bit assignments. */
#define S2650_PSL_C       0x01
#define S2650_PSL_COM     0x02
#define S2650_PSL_OVF     0x04
#define S2650_PSL_WC      0x08
#define S2650_PSL_RS      0x10
#define S2650_PSL_IDC     0x20
#define S2650_PSL_CC_MASK 0xc0

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
    uint32_t psu;                       /* writable PSU state, 8-bit */
    uint32_t psl;                       /* Program Status Lower, 8-bit */
    uint32_t ras[S2650_RETURN_STACK_DEPTH]; /* 15-bit return addresses */

    /* Fields up to this point are cleared by CPU reset. */
    struct {} end_reset_fields;

    /* External single-bit Sense input; it is not CPU-resettable storage. */
    uint32_t sense;
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
