/*
 * QEMU Toshiba MeP TCG translator
 *
 * The first execution slice intentionally covers only attested 16-bit
 * core-mode instructions.  MeP also has 32-bit core and coprocessor/VLIW
 * encodings; those remain explicit unsupported cases rather than being
 * guessed or silently skipped.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"
#include "cpu.h"
#include "tcg/tcg-op.h"
#include "exec/translator.h"
#include "exec/translation-block.h"
#include "exec/log.h"

typedef struct DisasContext {
    DisasContextBase base;
    CPUMEPState *env;
} DisasContext;

static TCGv_i32 cpu_gpr[MEP_NUM_GPRS];
static TCGv_i32 cpu_pc;
static char cpu_gpr_name[MEP_NUM_GPRS][8];

static int32_t mep_sext(unsigned int value, unsigned int bits)
{
    unsigned int sign = 1U << (bits - 1);

    return (int32_t)((value ^ sign) - sign);
}

static bool mep_translate_major0(DisasContext *ctx, uint16_t insn)
{
    unsigned int rn = (insn >> 8) & 0xf;
    unsigned int rm = (insn >> 4) & 0xf;
    unsigned int sub = insn & 0xf;

    switch (sub) {
    case 0x0: /* mov $rn,$rm; mov $0,$0 is the architectural nop alias */
        tcg_gen_mov_i32(cpu_gpr[rn], cpu_gpr[rm]);
        return true;
    case 0x4: /* sub $rn,$rm */
        tcg_gen_sub_i32(cpu_gpr[rn], cpu_gpr[rn], cpu_gpr[rm]);
        return true;
    case 0xa: { /* sw $rnl,($rma) */
        TCGv_i32 addr = tcg_temp_new_i32();

        tcg_gen_andi_i32(addr, cpu_gpr[rm], ~3U);
        tcg_gen_qemu_st_i32(cpu_gpr[rn], addr, 0, MO_LEUL);
        return true;
    }
    case 0xe: { /* lw $rnl,($rma) */
        TCGv_i32 addr = tcg_temp_new_i32();

        tcg_gen_andi_i32(addr, cpu_gpr[rm], ~3U);
        tcg_gen_qemu_ld_i32(cpu_gpr[rn], addr, 0, MO_LEUL);
        return true;
    }
    default:
        return false;
    }
}

static bool mep_translate_16(DisasContext *ctx, uint16_t insn)
{
    unsigned int major = insn >> 12;
    unsigned int rn = (insn >> 8) & 0xf;

    switch (major) {
    case 0x0:
        return mep_translate_major0(ctx, insn);

    case 0x5: /* mov $rn,$simm8 */
        tcg_gen_movi_i32(cpu_gpr[rn], (int8_t)(insn & 0xff));
        return true;

    case 0x6:
        if ((insn & 0x3) == 0) { /* add $rn,$simm6 */
            int32_t imm = mep_sext((insn >> 2) & 0x3f, 6);

            tcg_gen_addi_i32(cpu_gpr[rn], cpu_gpr[rn], imm);
            return true;
        }
        return false;

    default:
        return false;
    }
}

static void mep_tr_init_disas_context(DisasContextBase *dcbase,
                                      CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    ctx->env = cpu_env(cs);
}

static void mep_tr_tb_start(DisasContextBase *dcbase, CPUState *cs)
{
}

static void mep_tr_insn_start(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    tcg_gen_insn_start(ctx->base.pc_next, 0, 0);
}

static void mep_tr_translate_insn(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    uint32_t pc = ctx->base.pc_next;
    uint16_t insn = translator_lduw_end(ctx->env, &ctx->base, pc, MO_LE);

    if (!mep_translate_16(ctx, insn)) {
        qemu_log_mask(LOG_UNIMP,
                      "MeP: unsupported instruction 0x%04x at 0x%08x\n",
                      insn, pc);
        tcg_gen_movi_i32(cpu_pc, pc);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        return;
    }

    ctx->base.pc_next = pc + 2;
}

static void mep_tr_tb_stop(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    if (ctx->base.is_jmp != DISAS_NORETURN) {
        tcg_gen_movi_i32(cpu_pc, ctx->base.pc_next);
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps mep_tr_ops = {
    .init_disas_context = mep_tr_init_disas_context,
    .tb_start = mep_tr_tb_start,
    .insn_start = mep_tr_insn_start,
    .translate_insn = mep_tr_translate_insn,
    .tb_stop = mep_tr_tb_stop,
};

void mep_translate_code(CPUState *cs, TranslationBlock *tb,
                        int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc;

    translator_loop(cs, tb, max_insns, pc, host_pc, &mep_tr_ops, &dc.base,
                    TCG_TYPE_VA);
}

void mep_translate_init(void)
{
    unsigned int i;

    for (i = 0; i < MEP_NUM_GPRS; i++) {
        snprintf(cpu_gpr_name[i], sizeof(cpu_gpr_name[i]), "r%u", i);
        cpu_gpr[i] = tcg_global_mem_new_i32(
            tcg_env, offsetof(CPUMEPState, gpr) + i * sizeof(uint32_t),
            cpu_gpr_name[i]);
    }

    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                    offsetof(CPUMEPState, pc), "pc");
}
