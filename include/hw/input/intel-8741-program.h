/*
 * Intel 8741 UPI-41 experimental program execution subset.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_INTEL_8741_PROGRAM_H
#define HW_INPUT_INTEL_8741_PROGRAM_H

#include "hw/input/intel-8741.h"

#define INTEL_8741_PROGRAM_SIZE 1024
#define INTEL_8741_RAM_SIZE 64
#define INTEL_8741_PSW_C  0x80
#define INTEL_8741_PSW_AC 0x40
#define INTEL_8741_PSW_F0 0x20
#define INTEL_8741_PSW_BS 0x10
#define INTEL_8741_PSW_FIXED 0x08
#define INTEL_8741_PSW_SP 0x07

typedef struct Intel8741Program {
    uint16_t pc;
    uint8_t acc;
    /* F0 is owned by Intel8741Core; bit 3 is synthesized on reads. */
    uint8_t psw;
    uint8_t ram[INTEL_8741_RAM_SIZE];
} Intel8741Program;

typedef enum Intel8741StepResult {
    INTEL_8741_STEP_OK,
    INTEL_8741_STEP_INVALID,
    INTEL_8741_STEP_UNSUPPORTED,
    INTEL_8741_STEP_HANDSHAKE,
} Intel8741StepResult;

void intel_8741_program_reset(Intel8741Program *s);
uint8_t intel_8741_program_psw(const Intel8741Program *s,
                               const Intel8741Core *core);

/*
 * Execute at most one instruction from a complete 1 KiB ROM.
 * A failed step does not advance PC or modify accumulator or DBB.
 * This subset has no timer, interrupt, stack instructions or port execution
 * yet. The register banks and stack area share internal RAM.
 */
Intel8741StepResult intel_8741_program_step(Intel8741Program *s,
                                           Intel8741Core *core,
                                           const uint8_t *rom,
                                           size_t rom_size);

#endif
