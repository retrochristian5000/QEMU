/*
 * Intel 8741 UPI-41 experimental program execution subset.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef HW_INPUT_INTEL_8741_PROGRAM_H
#define HW_INPUT_INTEL_8741_PROGRAM_H

#include "hw/input/intel-8741.h"

#define INTEL_8741_PROGRAM_SIZE 1024

typedef struct Intel8741Program {
    uint16_t pc;
    uint8_t acc;
} Intel8741Program;

typedef enum Intel8741StepResult {
    INTEL_8741_STEP_OK,
    INTEL_8741_STEP_INVALID,
    INTEL_8741_STEP_UNSUPPORTED,
    INTEL_8741_STEP_HANDSHAKE,
} Intel8741StepResult;

void intel_8741_program_reset(Intel8741Program *s);

/*
 * Execute at most one instruction from a complete 1 KiB ROM.
 * A failed step does not advance PC or modify accumulator or DBB.
 * This subset has no timer, interrupt, RAM or port execution yet.
 */
Intel8741StepResult intel_8741_program_step(Intel8741Program *s,
                                           Intel8741Core *core,
                                           const uint8_t *rom,
                                           size_t rom_size);

#endif
