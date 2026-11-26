/*
 * Intel 8741 UPI-41 program execution subset.
 * SPDX-License-Identifier: GPL-2.0-or-later
 *
 * Intel MCS-48 and UPI-41 Assembly Language Manual, 9800255D,
 * December 1978, chapters 3 and 4. Implement polling and DBB transfer
 * instructions first. Do not silently execute UPI-41A-only opcodes
 * or pretend to execute the unimplemented instruction set.
 */

#include "qemu/osdep.h"
#include "hw/input/intel-8741-program.h"

#define PROGRAM_MASK (INTEL_8741_PROGRAM_SIZE - 1)

void intel_8741_program_reset(Intel8741Program *s)
{
    s->pc = 0;
    s->acc = 0;
}

Intel8741StepResult intel_8741_program_step(Intel8741Program *s,
                                           Intel8741Core *core,
                                           const uint8_t *rom,
                                           size_t rom_size)
{
    uint16_t next;
    uint8_t op, value;
    bool command, taken;

    if (!rom || rom_size != INTEL_8741_PROGRAM_SIZE ||
        s->pc >= INTEL_8741_PROGRAM_SIZE) {
        return INTEL_8741_STEP_INVALID;
    }

    op = rom[s->pc];
    next = (s->pc + 1) & PROGRAM_MASK;

    switch (op) {
    case 0x00: /* NOP */
        break;
    case 0x22: /* IN A,DBB */
        if (!intel_8741_mcu_read(core, &value, &command)) {
            return INTEL_8741_STEP_HANDSHAKE;
        }
        s->acc = value;
        break;
    case 0x02: /* OUT DBB,A */
        if (!intel_8741_mcu_write(core, s->acc)) {
            return INTEL_8741_STEP_HANDSHAKE;
        }
        break;
    case 0x23: /* MOV A,#data */
        s->acc = rom[next];
        next = (next + 1) & PROGRAM_MASK;
        break;
    case 0x86: /* JOBF */
    case 0xd6: /* JNIBF */
        taken = op == 0x86 ? !!(core->status & INTEL_8741_OBF) :
                             !(core->status & INTEL_8741_IBF);
        if (taken) {
            next = (next & 0x300) | rom[next];
        } else {
            next = (next + 1) & PROGRAM_MASK;
        }
        break;
    case 0x04: /* JMP page 0 */
    case 0x24: /* JMP page 1 */
    case 0x44: /* JMP page 2 */
    case 0x64: /* JMP page 3 */
        next = ((op & 0x60) << 3) | rom[next];
        break;
    default:
        return INTEL_8741_STEP_UNSUPPORTED;
    }

    s->pc = next;
    return INTEL_8741_STEP_OK;
}
