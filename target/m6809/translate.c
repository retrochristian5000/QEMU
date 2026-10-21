/* Motorola MC6809 minimal TCG skeleton.
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
    CPUM6809State *env;
} DisasContext;

static TCGv_i32 cpu_pc;

static void m6809_tr_init_disas_context(DisasContextBase *dcbase,
                                        CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    ctx->env = cpu_env(cs);
}

static void m6809_tr_tb_start(DisasContextBase *dcbase, CPUState *cs)
{
}

static void m6809_tr_insn_start(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    tcg_gen_insn_start(ctx->base.pc_next & M6809_ADDRESS_MASK, 0, 0);
}

static void m6809_tr_translate_insn(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    uint32_t pc = ctx->base.pc_next & M6809_ADDRESS_MASK;
    uint8_t opcode = translator_ldub(ctx->env, &ctx->base, pc);

    switch (opcode) {
    case 0x12: /* MC6809 NOP */
        ctx->base.pc_next = (pc + 1) & M6809_ADDRESS_MASK;
        break;
    default:
        /* No unverified opcode semantics or guessed byte lengths. */
        qemu_log_mask(LOG_UNIMP,
                      "MC6809: opcode 0x%02x not implemented at 0x%04x\n",
                      opcode, pc);
        tcg_gen_movi_i32(cpu_pc, pc);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        break;
    }
}

static void m6809_tr_tb_stop(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    if (ctx->base.is_jmp != DISAS_NORETURN) {
        tcg_gen_movi_i32(cpu_pc, ctx->base.pc_next & M6809_ADDRESS_MASK);
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps m6809_tr_ops = {
    .init_disas_context = m6809_tr_init_disas_context,
    .tb_start = m6809_tr_tb_start,
    .insn_start = m6809_tr_insn_start,
    .translate_insn = m6809_tr_translate_insn,
    .tb_stop = m6809_tr_tb_stop,
};

void m6809_translate_code(CPUState *cs, TranslationBlock *tb,
                          int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc;
    translator_loop(cs, tb, max_insns, pc, host_pc, &m6809_tr_ops, &dc.base,
                    TCG_TYPE_VA);
}

void m6809_translate_init(void)
{
    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                     offsetof(CPUM6809State, pc), "pc");
}
