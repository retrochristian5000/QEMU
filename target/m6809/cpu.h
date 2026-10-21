/* Motorola MC6809/MC6809E CPU state.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_M6809_CPU_H
#define QEMU_M6809_CPU_H
#include "cpu-qom.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"

#ifdef CONFIG_USER_ONLY
#error "MC6809 system emulation only"
#endif

#define M6809_ADDRESS_MASK 0xffffu
#define M6809_RESET_VECTOR 0xfffeu

#define M6809_CC_C 0x01
#define M6809_CC_V 0x02
#define M6809_CC_Z 0x04
#define M6809_CC_N 0x08
#define M6809_CC_I 0x10
#define M6809_CC_H 0x20
#define M6809_CC_F 0x40
#define M6809_CC_E 0x80

/* Target-local interrupt requests; hardware delivery is not yet modeled. */
#define CPU_INTERRUPT_NMI CPU_INTERRUPT_TGT_EXT_0
#define CPU_INTERRUPT_FIR CPU_INTERRUPT_TGT_EXT_1

typedef struct CPUArchState {
    /* D = (A << 8) | B, not a host-endian overlay. */
    uint32_t a, b;            /* architecturally 8-bit */
    uint32_t dp, cc;          /* architecturally 8-bit */
    uint32_t x, y, u, s, pc; /* architecturally 16-bit */
} CPUM6809State;

struct ArchCPU {
    CPUState parent_obj;
    CPUM6809State env;
};

struct M6809CPUClass {
    CPUClass parent_class;
    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

#define CPU_RESOLVING_TYPE TYPE_M6809_CPU

void m6809_translate_init(void);
void m6809_translate_code(CPUState *cs, TranslationBlock *tb,
                          int *max_insns, vaddr pc, void *host_pc);
#endif
