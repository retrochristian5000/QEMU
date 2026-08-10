/*
 * QEMU TriMedia TCG translator
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "cpu.h"
#include "opcode.h"
#include "tcg/tcg-op.h"
#include "exec/translator.h"
#include "exec/translation-block.h"
#include "exec/log.h"

typedef struct DisasContext {
    DisasContextBase base;
    CPUTrimediaState *env;
} DisasContext;

typedef struct TrimediaPendingWrite {
    bool valid;
    bool guarded;
    uint8_t dest;
    TCGv_i32 value;
    TCGv_i32 guard;
    TCGv_i32 old_dest;
} TrimediaPendingWrite;

static TCGv_i32 cpu_gpr[TRIMEDIA_NUM_GPRS];
static TCGv_i32 cpu_pc;
static char cpu_gpr_name[TRIMEDIA_NUM_GPRS][8];

static const char *trimedia_opcode_name(uint8_t opcode)
{
    switch (opcode) {
    case TRIMEDIA_OP_IGTRI:
        return "igtri";
    case TRIMEDIA_OP_IGEQI:
        return "igeqi";
    case TRIMEDIA_OP_ILESI:
        return "ilesi";
    case TRIMEDIA_OP_INEQI:
        return "ineqi";
    case TRIMEDIA_OP_IEQLI:
        return "ieqli";
    case TRIMEDIA_OP_IADDI:
        return "iaddi";
    case TRIMEDIA_OP_ILD16D:
        return "ild16d";
    case TRIMEDIA_OP_LD32D:
        return "ld32d";
    case TRIMEDIA_OP_ULD8D:
        return "uld8d";
    case TRIMEDIA_OP_LSRI:
        return "lsri";
    case TRIMEDIA_OP_ASRI:
        return "asri";
    case TRIMEDIA_OP_ASLI:
        return "asli";
    case TRIMEDIA_OP_IADD:
        return "iadd";
    case TRIMEDIA_OP_ISUB:
        return "isub";
    case TRIMEDIA_OP_IGEQ:
        return "igeq";
    case TRIMEDIA_OP_IGTR:
        return "igtr";
    case TRIMEDIA_OP_BITAND:
        return "bitand";
    case TRIMEDIA_OP_BITOR:
        return "bitor";
    case TRIMEDIA_OP_ASR:
        return "asr";
    case TRIMEDIA_OP_ASL:
        return "asl";
    case TRIMEDIA_OP_IMUL:
        return "imul";
    case TRIMEDIA_OP_H_ST32D:
        return "h_st32d";
    case TRIMEDIA_OP_ISUBI:
        return "isubi";
    case TRIMEDIA_OP_UGTR:
        return "ugtr";
    case TRIMEDIA_OP_UGTRI:
        return "ugtri";
    case TRIMEDIA_OP_UGEQ:
        return "ugeq";
    case TRIMEDIA_OP_UGEQI:
        return "ugeqi";
    case TRIMEDIA_OP_IEQL:
        return "ieql/ueql";
    case TRIMEDIA_OP_UEQLI:
        return "ueqli";
    case TRIMEDIA_OP_INEQ:
        return "ineq/uneq";
    case TRIMEDIA_OP_UNEQI:
        return "uneqi";
    case TRIMEDIA_OP_ULESI:
        return "ulesi";
    case TRIMEDIA_OP_ILEQI:
        return "ileqi";
    case TRIMEDIA_OP_ULEQI:
        return "uleqi";
    case TRIMEDIA_OP_CARRY:
        return "carry";
    case TRIMEDIA_OP_INONZERO:
        return "inonzero";
    case TRIMEDIA_OP_BITXOR:
        return "bitxor";
    case TRIMEDIA_OP_BITANDINV:
        return "bitandinv";
    case TRIMEDIA_OP_BITINV:
        return "bitinv";
    case TRIMEDIA_OP_SEX16:
        return "sex16";
    case TRIMEDIA_OP_LSR:
        return "lsr";
    case TRIMEDIA_OP_ROL:
        return "rol";
    case TRIMEDIA_OP_ROLI:
        return "roli";
    case TRIMEDIA_OP_JMPT:
        return "jmpt";
    case TRIMEDIA_OP_IJMPT:
        return "ijmpt";
    case TRIMEDIA_OP_JMPI:
        return "jmpi";
    case TRIMEDIA_OP_IJMPI:
        return "ijmpi";
    case TRIMEDIA_OP_JMPF:
        return "jmpf";
    case TRIMEDIA_OP_IJMPF:
        return "ijmpf";
    case TRIMEDIA_OP_IMM:
        return "iimm/uimm";
    case TRIMEDIA_OP_ILD8D:
        return "ild8d";
    case TRIMEDIA_OP_ULD16D:
        return "uld16d";
    case TRIMEDIA_OP_LD32R:
        return "ld32r";
    default:
        return "unknown";
    }
}

static TCGv_i32 trimedia_read_gpr(unsigned int reg)
{
    g_assert(reg < TRIMEDIA_NUM_GPRS);

    if (reg == 0) {
        return tcg_constant_i32(0);
    }
    if (reg == 1) {
        return tcg_constant_i32(1);
    }
    return cpu_gpr[reg];
}

static bool trimedia_valid_regs(const TrimediaDecodedOp *op)
{
    return op->dest < TRIMEDIA_NUM_GPRS &&
           op->src1 < TRIMEDIA_NUM_GPRS &&
           op->src2 < TRIMEDIA_NUM_GPRS &&
           (!op->guarded || op->guard < TRIMEDIA_NUM_GPRS);
}

static bool trimedia_modifier_in_range(int32_t value, int32_t low,
                                       int32_t high)
{
    return value >= low && value <= high;
}

static void trimedia_gen_variable_shift(TCGv_i32 dest, TCGv_i32 value,
                                        TCGv_i32 shift, uint8_t opcode)
{
    TCGv_i32 safe_shift = tcg_temp_new_i32();
    TCGv_i32 shifted = tcg_temp_new_i32();
    TCGv_i32 large_result;

    /* TCG shifts require an in-range count; TriMedia defines >= 32 itself. */
    tcg_gen_andi_i32(safe_shift, shift, 31);

    switch (opcode) {
    case TRIMEDIA_OP_ASL:
        tcg_gen_shl_i32(shifted, value, safe_shift);
        large_result = tcg_constant_i32(0);
        break;
    case TRIMEDIA_OP_ASR:
        tcg_gen_sar_i32(shifted, value, safe_shift);
        large_result = tcg_temp_new_i32();
        tcg_gen_sari_i32(large_result, value, 31);
        break;
    case TRIMEDIA_OP_LSR:
        tcg_gen_shr_i32(shifted, value, safe_shift);
        large_result = tcg_constant_i32(0);
        break;
    default:
        g_assert_not_reached();
    }

    tcg_gen_movcond_i32(TCG_COND_LTU, dest, shift, tcg_constant_i32(32),
                        shifted, large_result);
}

static void trimedia_gen_rotate_left(TCGv_i32 dest, TCGv_i32 value,
                                     TCGv_i32 shift)
{
    TCGv_i32 low_five = tcg_temp_new_i32();

    tcg_gen_andi_i32(low_five, shift, 31);
    tcg_gen_rotl_i32(dest, value, low_five);
}

/*
 * Generate one decoded latency-1 result without committing it to the
 * architectural register file.  All operations in a VLIW instruction read
 * the pre-instruction register state; results are committed only after every
 * issue slot has been generated.
 */
static bool trimedia_gen_decoded_op(const TrimediaDecodedOp *op,
                                    TrimediaPendingWrite *write)
{
    TCGv_i32 src1;
    TCGv_i32 src2;

    memset(write, 0, sizeof(*write));

    if (!trimedia_valid_regs(op)) {
        return false;
    }

    write->dest = op->dest;
    write->value = tcg_temp_new_i32();

    src1 = trimedia_read_gpr(op->src1);
    src2 = trimedia_read_gpr(op->src2);

    switch (op->opcode) {
    case TRIMEDIA_OP_IADD:
        tcg_gen_add_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_IADDI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_addi_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ISUB:
        tcg_gen_sub_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_ISUBI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_subi_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_BITAND:
        tcg_gen_and_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_BITOR:
        tcg_gen_or_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_BITXOR:
        tcg_gen_xor_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_BITANDINV:
        tcg_gen_andc_i32(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_BITINV:
        tcg_gen_not_i32(write->value, src1);
        break;
    case TRIMEDIA_OP_SEX16:
        tcg_gen_ext16s_i32(write->value, src1);
        break;
    case TRIMEDIA_OP_IEQL:
        tcg_gen_setcond_i32(TCG_COND_EQ, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_INEQ:
        tcg_gen_setcond_i32(TCG_COND_NE, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_IGEQ:
        tcg_gen_setcond_i32(TCG_COND_GE, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_IGTR:
        tcg_gen_setcond_i32(TCG_COND_GT, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_UGTR:
        tcg_gen_setcond_i32(TCG_COND_GTU, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_UGEQ:
        tcg_gen_setcond_i32(TCG_COND_GEU, write->value, src1, src2);
        break;
    case TRIMEDIA_OP_IEQLI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_EQ, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_INEQI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_NE, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_IGTRI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_GT, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_IGEQI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_GE, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ILESI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_LT, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ILEQI:
        if (!trimedia_modifier_in_range(op->modifier, -64, 63)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_LE, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_UGTRI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_GTU, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_UGEQI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_GEU, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_UEQLI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_EQ, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_UNEQI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_NE, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ULESI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_LTU, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ULEQI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 127)) {
            return false;
        }
        tcg_gen_setcondi_i32(TCG_COND_LEU, write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_CARRY:
    {
        TCGv_i32 sum = tcg_temp_new_i32();

        tcg_gen_add_i32(sum, src1, src2);
        tcg_gen_setcond_i32(TCG_COND_LTU, write->value, sum, src1);
        break;
    }
    case TRIMEDIA_OP_INONZERO:
        tcg_gen_movcond_i32(TCG_COND_EQ, write->value, src1,
                            tcg_constant_i32(0), src2,
                            tcg_constant_i32(0));
        break;
    case TRIMEDIA_OP_ASLI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 31)) {
            return false;
        }
        tcg_gen_shli_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ASRI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 31)) {
            return false;
        }
        tcg_gen_sari_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_LSRI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 31)) {
            return false;
        }
        tcg_gen_shri_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_ASL:
    case TRIMEDIA_OP_ASR:
    case TRIMEDIA_OP_LSR:
        trimedia_gen_variable_shift(write->value, src1, src2, op->opcode);
        break;
    case TRIMEDIA_OP_ROL:
        trimedia_gen_rotate_left(write->value, src1, src2);
        break;
    case TRIMEDIA_OP_ROLI:
        if (!trimedia_modifier_in_range(op->modifier, 0, 31)) {
            return false;
        }
        tcg_gen_rotli_i32(write->value, src1, op->modifier);
        break;
    case TRIMEDIA_OP_IMM:
        tcg_gen_movi_i32(write->value, op->modifier);
        break;
    default:
        /*
         * Latency-3 multiply, memory, and control-flow operations are known
         * but intentionally wait for their pipeline/delay-slot machinery.
         */
        return false;
    }

    /* Writes to architectural constant registers are prohibited. */
    if (op->dest < 2) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "TriMedia: discarded write to constant register r%u\n",
                      op->dest);
        return true;
    }

    write->valid = true;

    /* iimm/uimm are architecturally unguarded even though most ops may guard. */
    write->guarded = op->guarded && op->opcode != TRIMEDIA_OP_IMM;
    if (write->guarded) {
        write->guard = tcg_temp_new_i32();
        write->old_dest = tcg_temp_new_i32();
        tcg_gen_andi_i32(write->guard, trimedia_read_gpr(op->guard), 1);
        tcg_gen_mov_i32(write->old_dest, cpu_gpr[op->dest]);
    }

    return true;
}

static void trimedia_commit_write(const TrimediaPendingWrite *write)
{
    if (!write->valid) {
        return;
    }

    if (write->guarded) {
        tcg_gen_movcond_i32(TCG_COND_NE, cpu_gpr[write->dest], write->guard,
                            tcg_constant_i32(0), write->value,
                            write->old_dest);
    } else {
        tcg_gen_mov_i32(cpu_gpr[write->dest], write->value);
    }
}

static bool trimedia_gen_packet(const TrimediaDecodedPacket *packet,
                                uint8_t *unsupported_opcode)
{
    TrimediaPendingWrite write[TRIMEDIA_MAX_ISSUE_SLOTS] = { 0 };
    unsigned int i;

    if (packet->num_ops > TRIMEDIA_MAX_ISSUE_SLOTS) {
        return false;
    }

    for (i = 0; i < packet->num_ops; i++) {
        if (!trimedia_gen_decoded_op(&packet->op[i], &write[i])) {
            *unsupported_opcode = packet->op[i].opcode;
            return false;
        }
    }

    for (i = 0; i < packet->num_ops; i++) {
        trimedia_commit_write(&write[i]);
    }

    return true;
}

/*
 * Decode the packed TriMedia instruction stream into up to five operations.
 *
 * Philips documents the operation codes separately from the compressed VLIW
 * packing.  The latter uses variable-size operation encodings and format bits
 * associated with the preceding instruction.  Keep this boundary explicit so
 * that the semantic implementation above is not coupled to guessed bitfields.
 */
static bool trimedia_decode_packet(DisasContext *ctx,
                                   TrimediaDecodedPacket *packet)
{
    (void)ctx;
    memset(packet, 0, sizeof(*packet));
    return false;
}

static void trimedia_tr_init_disas_context(DisasContextBase *dcbase,
                                           CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    ctx->env = cpu_env(cs);
}

static void trimedia_tr_tb_start(DisasContextBase *dcbase, CPUState *cs)
{
}

static void trimedia_tr_insn_start(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    tcg_gen_insn_start(ctx->base.pc_next, 0, 0);
}

static void trimedia_tr_translate_insn(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    TrimediaDecodedPacket packet;
    uint8_t unsupported_opcode = 0xff;

    if (!trimedia_decode_packet(ctx, &packet)) {
        qemu_log_mask(LOG_UNIMP,
                      "TriMedia: VLIW packet decoder not implemented at "
                      "0x%08x\n", (uint32_t)ctx->base.pc_next);
        tcg_gen_movi_i32(cpu_pc, (uint32_t)ctx->base.pc_next);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        return;
    }

    if (packet.encoded_size == 0) {
        qemu_log_mask(LOG_GUEST_ERROR,
                      "TriMedia: decoded zero-length packet at 0x%08x\n",
                      (uint32_t)ctx->base.pc_next);
        tcg_gen_movi_i32(cpu_pc, (uint32_t)ctx->base.pc_next);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        return;
    }

    if (!trimedia_gen_packet(&packet, &unsupported_opcode)) {
        qemu_log_mask(LOG_UNIMP,
                      "TriMedia: operation %s (0x%02x) not implemented at "
                      "0x%08x\n", trimedia_opcode_name(unsupported_opcode),
                      unsupported_opcode, (uint32_t)ctx->base.pc_next);
        tcg_gen_movi_i32(cpu_pc, (uint32_t)ctx->base.pc_next);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        return;
    }

    ctx->base.pc_next += packet.encoded_size;
}

static void trimedia_tr_tb_stop(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    if (ctx->base.is_jmp != DISAS_NORETURN) {
        tcg_gen_movi_i32(cpu_pc, (uint32_t)ctx->base.pc_next);
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps trimedia_tr_ops = {
    .init_disas_context = trimedia_tr_init_disas_context,
    .tb_start = trimedia_tr_tb_start,
    .insn_start = trimedia_tr_insn_start,
    .translate_insn = trimedia_tr_translate_insn,
    .tb_stop = trimedia_tr_tb_stop,
};

void trimedia_translate_code(CPUState *cs, TranslationBlock *tb,
                             int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc;

    translator_loop(cs, tb, max_insns, pc, host_pc, &trimedia_tr_ops, &dc.base,
                    TCG_TYPE_VA);
}

void trimedia_translate_init(void)
{
    unsigned int i;

    for (i = 0; i < TRIMEDIA_NUM_GPRS; i++) {
        snprintf(cpu_gpr_name[i], sizeof(cpu_gpr_name[i]), "r%u", i);
        cpu_gpr[i] = tcg_global_mem_new_i32(
            tcg_env, offsetof(CPUTrimediaState, gpr) + i * sizeof(uint32_t),
            cpu_gpr_name[i]);
    }

    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                    offsetof(CPUTrimediaState, pc), "pc");
}
