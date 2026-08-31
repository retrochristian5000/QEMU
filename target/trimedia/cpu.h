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
#define TRIMEDIA_NUM_TIMERS 4

/*
 * PNX15xx timer event-source selector values.  The CONTROL register bit
 * layout is deliberately not encoded here until the TM3260 control fields
 * are recovered; these are the documented selector values themselves.
 */
typedef enum TrimediaTimerSource {
    TRIMEDIA_TIMER_SOURCE_CPU_CLOCK = 0,
    TRIMEDIA_TIMER_SOURCE_PRESCALE = 1,
    TRIMEDIA_TIMER_SOURCE_RESERVED = 2,
    TRIMEDIA_TIMER_SOURCE_DATABREAK = 3,
    TRIMEDIA_TIMER_SOURCE_INSTBREAK = 4,
    TRIMEDIA_TIMER_SOURCE_CACHE1 = 5,
    TRIMEDIA_TIMER_SOURCE_CACHE2 = 6,
    TRIMEDIA_TIMER_SOURCE_VDI_CLK1 = 7,
    TRIMEDIA_TIMER_SOURCE_VDI_CLK2 = 8,
    TRIMEDIA_TIMER_SOURCE_VDO_CLK1 = 9,
    TRIMEDIA_TIMER_SOURCE_VDO_CLK2 = 10,
    TRIMEDIA_TIMER_SOURCE_AI_WS = 11,
    TRIMEDIA_TIMER_SOURCE_AO_WS = 12,
    TRIMEDIA_TIMER_SOURCE_GPIO_TIMER0 = 13,
    TRIMEDIA_TIMER_SOURCE_GPIO_TIMER1 = 14,
    TRIMEDIA_TIMER_SOURCE_REFERENCE_CLOCK = 15,
} TrimediaTimerSource;

/* PNX15xx VIC source numbers for TIMER1, TIMER2, TIMER3, and SYSTIMER. */
typedef enum TrimediaTimerIRQ {
    TRIMEDIA_IRQ_TIMER1 = 5,
    TRIMEDIA_IRQ_TIMER2 = 6,
    TRIMEDIA_IRQ_TIMER3 = 7,
    TRIMEDIA_IRQ_SYSTIMER = 8,
} TrimediaTimerIRQ;

typedef struct TrimediaTimerState {
    uint32_t control;
    uint32_t modulus;
    uint32_t value;
} TrimediaTimerState;

typedef struct CPUArchState {
    uint32_t gpr[TRIMEDIA_NUM_GPRS];
    uint32_t pc;
    uint32_t pcsw;
    uint32_t dpc;
    uint32_t spc;
    uint32_t excvec;
    uint64_t cccount;

    /* TIMER1, TIMER2, TIMER3, then the system-software SYSTIMER. */
    TrimediaTimerState timers[TRIMEDIA_NUM_TIMERS];

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
