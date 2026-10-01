/*
 * Zilog Z80 CPU definitions
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_Z80_CPU_H
#define QEMU_Z80_CPU_H

#include "cpu-qom.h"
#include "exec/cpu-common.h"
#include "exec/cpu-interrupt.h"

#ifdef CONFIG_USER_ONLY
#error "Z80 does not support user mode emulation"
#endif

#define Z80_ADDRESS_MASK 0xffffu

/* F register bits. Keep the undocumented X/Y bits intact in raw F state. */
#define Z80_FLAG_C  0x01
#define Z80_FLAG_N  0x02
#define Z80_FLAG_PV 0x04
#define Z80_FLAG_X  0x08
#define Z80_FLAG_H  0x10
#define Z80_FLAG_Y  0x20
#define Z80_FLAG_Z  0x40
#define Z80_FLAG_S  0x80

/*
 * Store the programmer-visible 8-bit registers as their natural 16-bit
 * register pairs. This preserves the complete F register and keeps 16-bit
 * operations cheap without inventing host-endian aliases.
 */
typedef struct CPUArchState {
    uint32_t af;
    uint32_t bc;
    uint32_t de;
    uint32_t hl;

    uint32_t af2;
    uint32_t bc2;
    uint32_t de2;
    uint32_t hl2;

    uint32_t ix;
    uint32_t iy;
    uint32_t sp;
    uint32_t pc;

    uint32_t i;
    uint32_t r;
    uint32_t iff1;
    uint32_t iff2;
    uint32_t im;
} CPUZ80State;

struct ArchCPU {
    CPUState parent_obj;
    CPUZ80State env;
};

struct Z80CPUClass {
    CPUClass parent_class;

    DeviceRealize parent_realize;
    ResettablePhases parent_phases;
};

#define CPU_RESOLVING_TYPE TYPE_Z80_CPU

void z80_translate_init(void);
void z80_translate_code(CPUState *cs, TranslationBlock *tb,
                        int *max_insns, vaddr pc, void *host_pc);

#endif /* QEMU_Z80_CPU_H */
