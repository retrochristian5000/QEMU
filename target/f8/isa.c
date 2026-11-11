/*
 * Fairchild F8 / Mostek MK3870 opcode metadata.  No instruction execution.
 * Sources: Mostek 3870/F8 Data Book, F8 programming guide; MAME reference.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "isa.h"

#define INST(name, kind, count, imm) \
    ((F8Instruction){name, F8_OPCODE_DOCUMENTED, kind, count, imm})

F8Instruction f8_instruction(uint8_t op)
{
    static const char *const transfers[16] = {
        "LR A,KU", "LR A,KL", "LR A,QU", "LR A,QL",
        "LR KU,A", "LR KL,A", "LR QU,A", "LR QL,A",
        "LR K,P", "LR P,K", "LR A,IS", "LR IS,A",
        "PK", "LR P0,Q", "LR Q,DC", "LR DC,Q"
    };
    static const char *const misc[16] = {
        "LR DC,H", "LR H,DC", "SR 1", "SL 1",
        "SR 4", "SL 4", "LM", "ST",
        "COM", "LNK", "DI", "EI", "POP", "LR W,J", "LR J,W", "INC"
    };
    static const char *const immediate[13] = {
        "LI", "NI", "OI", "XI", "AI", "CI", "IN", "OUT",
        "PI", "JMP", "DCI", "NOP", "XDC"
    };
    static const char *const memory[7] = {
        "AM", "AMD", "NM", "OM", "XM", "CM", "ADC"
    };
    uint8_t lo = op & 15;
    uint8_t hi = op >> 4;

    if (op <= 0x0f) {
        return INST(transfers[op], F8_OPERAND_NONE, 1, 0);
    }
    if (op <= 0x1f) {
        return INST(misc[lo], F8_OPERAND_NONE, 1, 0);
    }
    if (op <= 0x2c) {
        if (op <= 0x27) {
            return INST(immediate[lo], F8_OPERAND_IMM8, 2, 0);
        }
        if (op <= 0x2a) {
            return INST(immediate[lo], F8_OPERAND_IMM16, 3, 0);
        }
        return INST(immediate[lo], F8_OPERAND_NONE, 1, 0);
    }
    if (op <= 0x2f) {
        return (F8Instruction){"?", F8_OPCODE_RESERVED, F8_OPERAND_NONE, 1, 0};
    }
    if ((hi >= 3 && hi <= 5) || hi >= 12) {
        static const char *const group[16] = {
            [3] = "DS", [4] = "LR A", [5] = "LR R,A",
            [12] = "AS", [13] = "ASD", [14] = "XS", [15] = "NS"
        };
        if (lo == 15) {
            return (F8Instruction){"?", F8_OPCODE_RESERVED, F8_OPERAND_NONE, 1, 0};
        }
        return INST(group[hi], lo < 12 ? F8_OPERAND_REG : F8_OPERAND_ISAR,
                    1, lo);
    }
    if (hi == 6) {
        return INST(lo < 8 ? "LISU" : "LISL", F8_OPERAND_CONST3,
                    1, lo & 7);
    }
    if (hi == 7) {
        return lo == 0 ? INST("CLR", F8_OPERAND_NONE, 1, 0) :
                         INST("LIS", F8_OPERAND_CONST4, 1, lo);
    }
    if (hi == 8) {
        if (lo < 8) {
            const char *name = lo == 1 || lo == 5 ? "BP" :
                               lo == 2 ? "BC" : lo == 4 ? "BZ" : "BT";
            return INST(name, (name[1] == 'T') ? F8_OPERAND_MASK_REL8 :
                        F8_OPERAND_REL8, 2, lo);
        }
        if (lo < 15) {
            return INST(memory[lo - 8], F8_OPERAND_NONE, 1, 0);
        }
        return INST("BR7", F8_OPERAND_REL8, 2, 0);
    }
    if (hi == 9) {
        const char *name = lo == 0 ? "BR" : lo == 1 || lo == 5 ? "BM" :
                           lo == 2 ? "BNC" : lo == 4 ? "BNZ" :
                           lo == 8 ? "BNO" : "BF";
        return INST(name, name[1] == 'F' ? F8_OPERAND_MASK_REL8 :
                    F8_OPERAND_REL8, 2, lo);
    }
    if (hi == 10 || hi == 11) {
        if (lo == 2 || lo == 3) {
            /* Sources differ for ports 2 and 3; do not alias to NOP. */
            return (F8Instruction){"?", F8_OPCODE_DISPUTED,
                                   F8_OPERAND_NONE, 1, 0};
        }
        return INST(hi == 10 ? "INS" : "OUTS", F8_OPERAND_PORT4,
                    1, lo);
    }
    return (F8Instruction){"?", F8_OPCODE_RESERVED, F8_OPERAND_NONE, 1, 0};
}

bool f8_decode_bytes(const uint8_t *bytes, size_t available,
                     F8Instruction *decoded)
{
    F8Instruction candidate;

    if (!bytes || !decoded || !available) {
        return false;
    }
    candidate = f8_instruction(bytes[0]);
    if (candidate.length > available) {
        return false;
    }
    *decoded = candidate;
    return true;
}
