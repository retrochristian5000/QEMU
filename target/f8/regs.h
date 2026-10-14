/*
 * Fairchild F8 programmable registers (also used by Mostek MK3870).
 * ISA-visible register state, not an electrical reset or TCG CPU backend.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef TARGET_F8_REGS_H
#define TARGET_F8_REGS_H

#include <stdbool.h>
#include <stdint.h>

#define F8_SCRATCHPAD_SIZE 64U
#define F8_ISAR_MASK 0x3fU
#define F8_STATUS_MASK 0x1fU

/* W register: I/O/Z/C/S are five independent bits, not an 8-bit PSW. */
#define F8_W_SIGN      0x01U
#define F8_W_CARRY     0x02U
#define F8_W_ZERO      0x04U
#define F8_W_OVERFLOW  0x08U
#define F8_W_INTERRUPT 0x10U

#define F8_SCRATCH_J 9U
#define F8_SCRATCH_HU 10U
#define F8_SCRATCH_HL 11U
#define F8_SCRATCH_KU 12U
#define F8_SCRATCH_KL 13U
#define F8_SCRATCH_QU 14U
#define F8_SCRATCH_QL 15U

/* The 3850 contains these; its memory support chips hold address counters. */
typedef struct F8CoreRegisters {
    uint8_t a;
    uint8_t w;
    uint8_t isar;
    uint8_t scratchpad[F8_SCRATCHPAD_SIZE];
} F8CoreRegisters;

/* Architectural state of the complete F8 *system* or integrated MK3870. */
typedef struct F8AddressRegisters {
    uint16_t pc0;
    uint16_t pc1;  /* One return-address latch, not a RAM stack pointer. */
    uint16_t dc0;
    uint16_t dc1;  /* Availability depends on the memory-support chip. */
} F8AddressRegisters;

typedef struct F8Registers {
    F8CoreRegisters core;
    F8AddressRegisters addr;
} F8Registers;

typedef enum F8ScratchPair {
    F8_PAIR_H,  /* Scratchpad 10:11, high byte first. */
    F8_PAIR_K,  /* Scratchpad 12:13, high byte first. */
    F8_PAIR_Q,  /* Scratchpad 14:15, high byte first. */
} F8ScratchPair;

/* Deterministic initialization only: hardware power-on/reset is separate. */
void f8_regs_init_for_test(F8Registers *regs);
void f8_regs_set_w(F8CoreRegisters *core, uint8_t value);
void f8_regs_set_isar(F8CoreRegisters *core, uint8_t value);
void f8_regs_set_isar_upper(F8CoreRegisters *core, uint8_t upper);
void f8_regs_set_isar_lower(F8CoreRegisters *core, uint8_t lower);

/* Instruction operand nibbles 0..11 direct, C=IS, D=IS+, E=IS-;
 * F is undefined.  When successful, D/E affect only low 3 ISAR bits.
 * Invalid forms leave all state (including the output) untouched.
 */
bool f8_regs_scratch_index(F8CoreRegisters *core, uint8_t spec,
                           uint8_t *index);
bool f8_regs_read_scratch(F8CoreRegisters *core, uint8_t spec,
                          uint8_t *value);
bool f8_regs_write_scratch(F8CoreRegisters *core, uint8_t spec,
                           uint8_t value);

/* Aliases for H/K/Q; no extra, independent 16-bit storage. */
bool f8_regs_get_pair(const F8CoreRegisters *core, F8ScratchPair pair,
                      uint16_t *value);
bool f8_regs_set_pair(F8CoreRegisters *core, F8ScratchPair pair,
                      uint16_t value);

/* Transfer helpers for LR A,IS / LR IS,A / LR W,J / LR J,W. */
void f8_regs_isar_to_a(F8CoreRegisters *core);
void f8_regs_a_to_isar(F8CoreRegisters *core);
void f8_regs_j_to_w(F8CoreRegisters *core);
void f8_regs_w_to_j(F8CoreRegisters *core);

#endif /* TARGET_F8_REGS_H */
