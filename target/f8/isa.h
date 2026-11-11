/*
 * Fairchild F8 / Mostek MK3870 instruction metadata.
 *
 * This is a source-auditable decoder, not a QEMU TCG CPU backend.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef TARGET_F8_ISA_H
#define TARGET_F8_ISA_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum F8OpcodeStatus {
    F8_OPCODE_DOCUMENTED,
    F8_OPCODE_DISPUTED,
    F8_OPCODE_RESERVED,
} F8OpcodeStatus;

typedef enum F8OperandKind {
    F8_OPERAND_NONE,
    F8_OPERAND_IMM8,
    F8_OPERAND_IMM16,
    F8_OPERAND_REL8,
    F8_OPERAND_REG,
    F8_OPERAND_ISAR,
    F8_OPERAND_CONST3,
    F8_OPERAND_CONST4,
    F8_OPERAND_PORT4,
    F8_OPERAND_MASK_REL8,
} F8OperandKind;

typedef struct F8Instruction {
    const char *mnemonic;
    F8OpcodeStatus status;
    F8OperandKind operand_kind;
    uint8_t length;
    uint8_t operand; /* Instruction's encoded nibble, register, or bit mask. */
} F8Instruction;

/* Total for every byte value, including reserved/disputed opcodes. */
F8Instruction f8_instruction(uint8_t opcode);
/* Does not read beyond the supplied stream.  No speculative NOP aliases. */
bool f8_decode_bytes(const uint8_t *bytes, size_t available,
                     F8Instruction *decoded);

#endif /* TARGET_F8_ISA_H */
