/*
 * QEMU Zilog Z80 TCG translator
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
    CPUZ80State *env;
} DisasContext;

static TCGv_i32 cpu_af;
static TCGv_i32 cpu_bc;
static TCGv_i32 cpu_de;
static TCGv_i32 cpu_hl;
static TCGv_i32 cpu_af2;
static TCGv_i32 cpu_bc2;
static TCGv_i32 cpu_de2;
static TCGv_i32 cpu_hl2;
static TCGv_i32 cpu_ix;
static TCGv_i32 cpu_iy;
static TCGv_i32 cpu_sp;
static TCGv_i32 cpu_pc;
static TCGv_i32 cpu_i;
static TCGv_i32 cpu_r;
static TCGv_i32 cpu_iff1;
static TCGv_i32 cpu_iff2;
static TCGv_i32 cpu_im;

static void z80_tr_init_disas_context(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    ctx->env = cpu_env(cs);
}

static void z80_tr_tb_start(DisasContextBase *dcbase, CPUState *cs)
{
}

static void z80_tr_insn_start(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    tcg_gen_insn_start(ctx->base.pc_next & Z80_ADDRESS_MASK, 0, 0);
}

static void z80_tr_translate_insn(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);
    uint32_t pc = ctx->base.pc_next & Z80_ADDRESS_MASK;
    uint8_t opcode = translator_ldub(ctx->env, &ctx->base, pc);

    switch (opcode) {
    case 0x00: /* NOP */
        ctx->base.pc_next = (pc + 1) & Z80_ADDRESS_MASK;
        break;
    default:
        /*
         * Stop on unknown instructions rather than guessing opcode length,
         * prefix behavior, flags, timing, or side effects.
         */
        qemu_log_mask(LOG_UNIMP,
                      "Z80: opcode 0x%02x not implemented at 0x%04x\n",
                      opcode, pc);
        tcg_gen_movi_i32(cpu_pc, pc);
        tcg_gen_exit_tb(NULL, 0);
        ctx->base.is_jmp = DISAS_NORETURN;
        break;
    }
}

static void z80_tr_tb_stop(DisasContextBase *dcbase, CPUState *cs)
{
    DisasContext *ctx = container_of(dcbase, DisasContext, base);

    if (ctx->base.is_jmp != DISAS_NORETURN) {
        tcg_gen_movi_i32(cpu_pc, ctx->base.pc_next & Z80_ADDRESS_MASK);
        tcg_gen_exit_tb(NULL, 0);
    }
}

static const TranslatorOps z80_tr_ops = {
    .init_disas_context = z80_tr_init_disas_context,
    .tb_start = z80_tr_tb_start,
    .insn_start = z80_tr_insn_start,
    .translate_insn = z80_tr_translate_insn,
    .tb_stop = z80_tr_tb_stop,
};

void z80_translate_code(CPUState *cs, TranslationBlock *tb,
                        int *max_insns, vaddr pc, void *host_pc)
{
    DisasContext dc;

    translator_loop(cs, tb, max_insns, pc, host_pc, &z80_tr_ops, &dc.base,
                    TCG_TYPE_VA);
}

void z80_translate_init(void)
{
#define Z80_GLOBAL(field) \
    cpu_##field = tcg_global_mem_new_i32( \
        tcg_env, offsetof(CPUZ80State, field), #field)

    Z80_GLOBAL(af);
    Z80_GLOBAL(bc);
    Z80_GLOBAL(de);
    Z80_GLOBAL(hl);
    Z80_GLOBAL(af2);
    Z80_GLOBAL(bc2);
    Z80_GLOBAL(de2);
    Z80_GLOBAL(hl2);
    Z80_GLOBAL(ix);
    Z80_GLOBAL(iy);
    Z80_GLOBAL(sp);
    Z80_GLOBAL(pc);
    Z80_GLOBAL(i);
    Z80_GLOBAL(r);
    Z80_GLOBAL(iff1);
    Z80_GLOBAL(iff2);
    Z80_GLOBAL(im);

#undef Z80_GLOBAL

    /* Most globals become active as the verified decoder grows past NOP. */
    (void)cpu_af;
    (void)cpu_bc;
    (void)cpu_de;
    (void)cpu_hl;
    (void)cpu_af2;
    (void)cpu_bc2;
    (void)cpu_de2;
    (void)cpu_hl2;
    (void)cpu_ix;
    (void)cpu_iy;
    (void)cpu_sp;
    (void)cpu_i;
    (void)cpu_r;
    (void)cpu_iff1;
    (void)cpu_iff2;
    (void)cpu_im;
}
