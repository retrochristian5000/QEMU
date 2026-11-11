/*
 * TriMedia operation definitions
 *
 * The operation codes below are from the PNX1300 Series Data Book,
 * Appendix A.  This file describes decoded operations; the compressed
 * VLIW instruction-stream unpacker is intentionally kept separate.
 *
 * Keep this table limited to the PNX1300/TM3260 instruction-set generation.
 * Later TriMedia-family extensions belong behind separate CPU feature bits.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#ifndef QEMU_TRIMEDIA_OPCODE_H
#define QEMU_TRIMEDIA_OPCODE_H

#define TRIMEDIA_MAX_ISSUE_SLOTS 5

typedef enum TrimediaOpcode {
    TRIMEDIA_OP_IGTRI       = 0,
    TRIMEDIA_OP_IGEQI       = 1,
    TRIMEDIA_OP_ILESI       = 2,
    TRIMEDIA_OP_INEQI       = 3,
    TRIMEDIA_OP_IEQLI       = 4,
    TRIMEDIA_OP_IADDI       = 5,
    TRIMEDIA_OP_ILD16D      = 6,
    TRIMEDIA_OP_LD32D       = 7,
    TRIMEDIA_OP_ULD8D       = 8,
    TRIMEDIA_OP_LSRI        = 9,
    TRIMEDIA_OP_ASRI        = 10,
    TRIMEDIA_OP_ASLI        = 11,
    TRIMEDIA_OP_IADD        = 12,
    TRIMEDIA_OP_ISUB        = 13,
    TRIMEDIA_OP_IGEQ        = 14,
    TRIMEDIA_OP_IGTR        = 15,
    TRIMEDIA_OP_BITAND      = 16,
    TRIMEDIA_OP_BITOR       = 17,
    TRIMEDIA_OP_ASR         = 18,
    TRIMEDIA_OP_ASL         = 19,

    /* Latency-3 multiply: known opcode, execution intentionally deferred. */
    TRIMEDIA_OP_IMUL        = 27,

    /* Hardware store opcode used after scheduler pseudo-op lowering. */
    TRIMEDIA_OP_H_ST32D     = 31,
    TRIMEDIA_OP_ISUBI       = 32,
    TRIMEDIA_OP_UGTR        = 33,
    TRIMEDIA_OP_UGTRI       = 34,
    TRIMEDIA_OP_UGEQ        = 35,
    TRIMEDIA_OP_UGEQI       = 36,
    TRIMEDIA_OP_IEQL        = 37,
    TRIMEDIA_OP_UEQLI       = 38,
    TRIMEDIA_OP_INEQ        = 39,
    TRIMEDIA_OP_UNEQI       = 40,
    TRIMEDIA_OP_ULESI       = 41,
    TRIMEDIA_OP_ILEQI       = 42,
    TRIMEDIA_OP_ULEQI       = 43,
    TRIMEDIA_OP_CARRY       = 45,
    TRIMEDIA_OP_INONZERO    = 47,
    TRIMEDIA_OP_BITXOR      = 48,
    TRIMEDIA_OP_BITANDINV   = 49,
    TRIMEDIA_OP_BITINV      = 50,
    TRIMEDIA_OP_SEX16       = 51,
    TRIMEDIA_OP_LSR         = 96,
    TRIMEDIA_OP_ROL         = 97,
    TRIMEDIA_OP_ROLI        = 98,

    /* Control-flow operations; semantics are added after delay-slot support. */
    TRIMEDIA_OP_JMPT        = 176,
    TRIMEDIA_OP_IJMPT       = 177,
    TRIMEDIA_OP_JMPI        = 178,
    TRIMEDIA_OP_IJMPI       = 179,
    TRIMEDIA_OP_JMPF        = 180,
    TRIMEDIA_OP_IJMPF       = 181,

    /* iimm and uimm share operation code 191. */
    TRIMEDIA_OP_IMM         = 191,
    TRIMEDIA_OP_ILD8D       = 192,
    TRIMEDIA_OP_ULD16D      = 197,
    TRIMEDIA_OP_LD32R       = 200,
} TrimediaOpcode;

/*
 * ueql/uneq use the same hardware operation codes as ieql/ineq.  Likewise,
 * borrow, iles, ileq, lsl/lsli, sex8 and zex16 are scheduler/compiler pseudo
 * operations built from base PNX1300 operations, so they deliberately do not
 * receive duplicate hardware opcode entries here.
 */

/*
 * Canonical representation after VLIW decompression and operand extraction.
 * Only the least-significant bit of guard is architecturally significant.
 * modifier contains the sign/zero-extended immediate selected by the opcode.
 */
typedef struct TrimediaDecodedOp {
    uint8_t opcode;
    uint8_t dest;
    uint8_t src1;
    uint8_t src2;
    uint8_t guard;
    bool guarded;
    int32_t modifier;
} TrimediaDecodedOp;

typedef struct TrimediaDecodedPacket {
    TrimediaDecodedOp op[TRIMEDIA_MAX_ISSUE_SLOTS];
    unsigned int num_ops;
    unsigned int encoded_size;
} TrimediaDecodedPacket;

#endif /* QEMU_TRIMEDIA_OPCODE_H */
