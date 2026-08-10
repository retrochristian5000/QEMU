/*
 * QEMU Signetics 2650 TCG translator skeleton
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
    CPUS2650State *env;
} DisasContext;

static TCGv_i32 cpu_gpr[S2650_NUM_GPRS];
static TCGv_i32 cpu_pc;
static TCGv_i32 cpu_psu;
static TCGv_i32 cpu_psl;
static char cpu_gpr_name[S2650_NUM_GPRS][8];

static void s2650_tr_init_disas_context(DisasContextBase *dcbase,
                                        CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    ctx->env = cpu_env(cs);
}

static void s2650_tr_tb_start(DisasContextBase *dcbase, CPUState *cs)
{
}

static void s2650_tr_insn_start(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    tcg_gen_insn_start(ctx->base.pc_next & S2650_ADDRESS_MASK, 0, 0);
}

static void s2650_tr_translate_insn(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    uint32_t pc = ctx->base.pc_next & S2650_ADDRESS_MASK;

    /*
     * Do not guess instruction length or addressing semantics.  The 2650 has
     * one-, two-, and three-byte instructions plus paged, relative, indexed,
     * and indirect addressing.  Keep PC fixed until the real decoder lands.
     */
    qemu_log_mask(LOG_UNIMP,
                  "Signetics 2650: instruction decoder not implemented at "
                  "0x%04x\n", pc);
    tcg_gen_movi_i32(cpu_pc, pc);
    tcg_gen_exit_tb(NULL, 0);
    ctx->base.is_jmp = DISAS_NORETURN;
}

static void s2650_tr_tb_stop(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    if (ctx->base.is_jmp != DISAS_NORETURN) {
        tcg_gen_movi_i32(cpu_pc,
                         ctx->base.pc_next & S2650_ADDRESS_MASK);
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps s2650_tr_ops = {
    .init_disas_context = s2650_tr_init_disas_context,
    .tb_start = s2650_tr_tb_start,
    .insn_start = s2650_tr_insn_start,
    .translate_insn = s2650_tr_translate_insn,
    .tb_stop = s2650_tr_tb_stop,
};

void s2650_translate_code(CPUState *cs, TranslationBlock *tb,
                          int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc;

    translator_loop(cs, tb, max_insns, pc, host_pc, &s2650_tr_ops, &dc.base,
                    TCG_TYPE_VA);
}

void s2650_translate_init(void)
{
    unsigned int i;

    for (i = 0; i < S2650_NUM_GPRS; i++) {
        snprintf(cpu_gpr_name[i], sizeof(cpu_gpr_name[i]), "r%u", i);
        cpu_gpr[i] = tcg_global_mem_new_i32(
            tcg_env, offsetof(CPUS2650State, gpr) + i * sizeof(uint32_t),
            cpu_gpr_name[i]);
    }

    cpu_pc = tcg_global_mem_new_i32(tcg_env,
                                    offsetof(CPUS2650State, pc), "pc");
    cpu_psu = tcg_global_mem_new_i32(tcg_env,
                                     offsetof(CPUS2650State, psu), "psu");
    cpu_psl = tcg_global_mem_new_i32(tcg_env,
                                     offsetof(CPUS2650State, psl), "psl");

    /* Silence unused-global diagnostics until opcode generation consumes them. */
    (void)cpu_gpr;
    (void)cpu_psu;
    (void)cpu_psl;
}
