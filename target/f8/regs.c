/*
 * Fairchild F8 register access primitives (no instruction execution).
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "regs.h"

#include <string.h>

void f8_regs_init_for_test(F8Registers *regs)
{
    if (regs) {
        memset(regs, 0, sizeof(*regs));
    }
}

void f8_regs_set_w(F8CoreRegisters *core, uint8_t value)
{
    core->w = value & F8_STATUS_MASK;
}

void f8_regs_set_isar(F8CoreRegisters *core, uint8_t value)
{
    core->isar = value & F8_ISAR_MASK;
}

void f8_regs_set_isar_upper(F8CoreRegisters *core, uint8_t upper)
{
    core->isar = (core->isar & 7U) | ((upper & 7U) << 3);
}

void f8_regs_set_isar_lower(F8CoreRegisters *core, uint8_t lower)
{
    core->isar = (core->isar & 0x38U) | (lower & 7U);
}

bool f8_regs_scratch_index(F8CoreRegisters *core, uint8_t spec,
                           uint8_t *index)
{
    uint8_t old;

    if (!core || !index || spec > 14) {
        return false;
    }
    if (spec < 12) {
        *index = spec;
        return true;
    }
    old = core->isar & F8_ISAR_MASK;
    *index = old;
    if (spec == 13) {
        /* Only the low octal digit changes: 0'27' + 1 = 0'20'. */
        core->isar = (old & 0x38U) | ((old + 1U) & 7U);
    } else if (spec == 14) {
        /* Only the low octal digit changes: 0'20' - 1 = 0'27'. */
        core->isar = (old & 0x38U) | ((old - 1U) & 7U);
    }
    return true;
}

bool f8_regs_read_scratch(F8CoreRegisters *core, uint8_t spec,
                          uint8_t *value)
{
    uint8_t index;

    if (!value || !f8_regs_scratch_index(core, spec, &index)) {
        return false;
    }
    *value = core->scratchpad[index];
    return true;
}

bool f8_regs_write_scratch(F8CoreRegisters *core, uint8_t spec,
                           uint8_t value)
{
    uint8_t index;

    if (!f8_regs_scratch_index(core, spec, &index)) {
        return false;
    }
    core->scratchpad[index] = value;
    return true;
}

static bool f8_pair_index(F8ScratchPair pair, unsigned *index)
{
    switch (pair) {
    case F8_PAIR_H:
        *index = F8_SCRATCH_HU;
        return true;
    case F8_PAIR_K:
        *index = F8_SCRATCH_KU;
        return true;
    case F8_PAIR_Q:
        *index = F8_SCRATCH_QU;
        return true;
    default:
        return false;
    }
}

bool f8_regs_get_pair(const F8CoreRegisters *core, F8ScratchPair pair,
                      uint16_t *value)
{
    unsigned index;

    if (!core || !value || !f8_pair_index(pair, &index)) {
        return false;
    }
    *value = ((uint16_t)core->scratchpad[index] << 8) |
             core->scratchpad[index + 1];
    return true;
}

bool f8_regs_set_pair(F8CoreRegisters *core, F8ScratchPair pair,
                      uint16_t value)
{
    unsigned index;

    if (!core || !f8_pair_index(pair, &index)) {
        return false;
    }
    core->scratchpad[index] = value >> 8;
    core->scratchpad[index + 1] = value;
    return true;
}

void f8_regs_isar_to_a(F8CoreRegisters *core)
{
    core->a = core->isar & F8_ISAR_MASK;
}

void f8_regs_a_to_isar(F8CoreRegisters *core)
{
    f8_regs_set_isar(core, core->a);
}

void f8_regs_j_to_w(F8CoreRegisters *core)
{
    f8_regs_set_w(core, core->scratchpad[F8_SCRATCH_J]);
}

void f8_regs_w_to_j(F8CoreRegisters *core)
{
    core->scratchpad[F8_SCRATCH_J] = core->w & F8_STATUS_MASK;
}
