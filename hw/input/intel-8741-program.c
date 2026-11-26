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
    /* Deterministic initialization for the experimental core. */
    memset(s, 0, sizeof(*s));
}

uint8_t intel_8741_program_psw(const Intel8741Program *s,
                               const Intel8741Core *core)
{
    return (s->psw & ~(INTEL_8741_PSW_F0 | INTEL_8741_PSW_FIXED)) |
           INTEL_8741_PSW_FIXED |
           ((core->status & INTEL_8741_F0) ? INTEL_8741_PSW_F0 : 0);
}

static void intel_8741_write_psw(Intel8741Program *s, Intel8741Core *core,
                                uint8_t value)
{
    s->psw = value & ~(INTEL_8741_PSW_F0 | INTEL_8741_PSW_FIXED);
    intel_8741_mcu_set_f0(core, !!(value & INTEL_8741_PSW_F0));
}

static uint8_t *intel_8741_reg(Intel8741Program *s, unsigned int reg)
{
    return &s->ram[(s->psw & INTEL_8741_PSW_BS ? 24 : 0) + reg];
}

static uint8_t *intel_8741_indirect(Intel8741Program *s, unsigned int reg)
{
    return &s->ram[*intel_8741_reg(s, reg) & (INTEL_8741_RAM_SIZE - 1)];
}

static void intel_8741_add(Intel8741Program *s, uint8_t value, bool with_carry)
{
    unsigned int carry = with_carry && (s->psw & INTEL_8741_PSW_C);
    unsigned int sum = s->acc + value + carry;
    unsigned int low = (s->acc & 0xf) + (value & 0xf) + carry;

    s->psw &= ~(INTEL_8741_PSW_C | INTEL_8741_PSW_AC);
    if (sum > UINT8_MAX) {
        s->psw |= INTEL_8741_PSW_C;
    }
    if (low > 0xf) {
        s->psw |= INTEL_8741_PSW_AC;
    }
    s->acc = sum;
}

Intel8741StepResult intel_8741_program_step(Intel8741Program *s,
                                           Intel8741Core *core,
                                           const uint8_t *rom,
                                           size_t rom_size)
{
    uint16_t next;
    uint8_t op, value;
    uint8_t *reg;
    bool command, taken;

    if (!rom || rom_size != INTEL_8741_PROGRAM_SIZE ||
        s->pc >= INTEL_8741_PROGRAM_SIZE) {
        return INTEL_8741_STEP_INVALID;
    }

    op = rom[s->pc];
    next = (s->pc + 1) & PROGRAM_MASK;

    /* Contiguous register opcode groups all address the active bank. */
    switch (op & 0xf8) {
    case 0x18: /* INC Rn */
        ++*intel_8741_reg(s, op & 7);
        goto complete;
    case 0xc8: /* DEC Rn */
        --*intel_8741_reg(s, op & 7);
        goto complete;
    case 0x28: /* XCH A,Rn */
        reg = intel_8741_reg(s, op & 7);
        value = *reg;
        *reg = s->acc;
        s->acc = value;
        goto complete;
    case 0xa8: /* MOV Rn,A */
        *intel_8741_reg(s, op & 7) = s->acc;
        goto complete;
    case 0xb8: /* MOV Rn,#data */
        *intel_8741_reg(s, op & 7) = rom[next];
        next = (next + 1) & PROGRAM_MASK;
        goto complete;
    case 0xf8: /* MOV A,Rn */
        s->acc = *intel_8741_reg(s, op & 7);
        goto complete;
    case 0x68: /* ADD A,Rn */
    case 0x78: /* ADDC A,Rn */
        intel_8741_add(s, *intel_8741_reg(s, op & 7), (op & 0x10) != 0);
        goto complete;
    default:
        break;
    }

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
    case 0xc5: /* SEL RB0 */
        s->psw &= ~INTEL_8741_PSW_BS;
        break;
    case 0xd5: /* SEL RB1 */
        s->psw |= INTEL_8741_PSW_BS;
        break;
    case 0xc7: /* MOV A,PSW */
        s->acc = intel_8741_program_psw(s, core);
        break;
    case 0xd7: /* MOV PSW,A */
        intel_8741_write_psw(s, core, s->acc);
        break;
    case 0x85: /* CLR F0 */
        intel_8741_mcu_set_f0(core, false);
        break;
    case 0x95: /* CPL F0 */
        intel_8741_mcu_set_f0(core, !(core->status & INTEL_8741_F0));
        break;
    case 0xa5: /* CLR F1 */
        intel_8741_mcu_set_f1(core, false);
        break;
    case 0xb5: /* CPL F1 */
        intel_8741_mcu_set_f1(core, !(core->status & INTEL_8741_F1));
        break;
    case 0x97: /* CLR C */
        s->psw &= ~INTEL_8741_PSW_C;
        break;
    case 0xa7: /* CPL C */
        s->psw ^= INTEL_8741_PSW_C;
        break;
    case 0x17: /* INC A */
        s->acc++;
        break;
    case 0x07: /* DEC A */
        s->acc--;
        break;
    case 0xa0: /* MOV @R0,A */
    case 0xa1: /* MOV @R1,A */
        *intel_8741_indirect(s, op & 1) = s->acc;
        break;
    case 0xb0: /* MOV @R0,#data */
    case 0xb1: /* MOV @R1,#data */
        *intel_8741_indirect(s, op & 1) = rom[next];
        next = (next + 1) & PROGRAM_MASK;
        break;
    case 0xf0: /* MOV A,@R0 */
    case 0xf1: /* MOV A,@R1 */
        s->acc = *intel_8741_indirect(s, op & 1);
        break;
    case 0x10: /* INC @R0 */
    case 0x11: /* INC @R1 */
        ++*intel_8741_indirect(s, op & 1);
        break;
    case 0x20: /* XCH A,@R0 */
    case 0x21: /* XCH A,@R1 */
        reg = intel_8741_indirect(s, op & 1);
        value = *reg;
        *reg = s->acc;
        s->acc = value;
        break;
    case 0x03: /* ADD A,#data */
    case 0x13: /* ADDC A,#data */
        intel_8741_add(s, rom[next], (op & 0x10) != 0);
        next = (next + 1) & PROGRAM_MASK;
        break;
    case 0x60: /* ADD A,@R0 */
    case 0x61: /* ADD A,@R1 */
    case 0x70: /* ADDC A,@R0 */
    case 0x71: /* ADDC A,@R1 */
        intel_8741_add(s, *intel_8741_indirect(s, op & 1), (op & 0x10) != 0);
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

complete:
    s->pc = next;
    return INTEL_8741_STEP_OK;
}
