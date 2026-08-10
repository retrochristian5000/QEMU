/*
 * QEMU TriMedia TCG translator skeleton
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
    CPUTrimediaState *env;
} DisasContext;

static TCGv_i32 cpu_pc;

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

    /*
     * The target skeleton deliberately does not guess an instruction length
     * or encoding.  Keep the architectural PC unchanged and leave the TB so
     * that adding the real PNX1300/TM3260 decoder is an explicit next step.
     */
    qemu_log_mask(LOG_UNIMP,
                  "TriMedia: instruction decoder not implemented at 0x%08x\n",
                  (uint32_t)ctx->base.pc_next);
    tcg_gen_movi_i32(cpu_pc, (uint32_t)ctx->base.pc_next);
    tcg_gen_exit_tb(NULL, 0);
    ctx->base.is_jmp = DISAS_NORETURN;
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
    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                    offsetof(CPUTrimediaState, pc), "pc");
}
