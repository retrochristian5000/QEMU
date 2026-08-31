/*
 * Architectural EFLAGS corrections shared by the i386 emitters.
 *
 * Keep these overrides outside the large emitter files so the WHP split
 * between generic i386 and original 16-bit x86 remains small and auditable.
 */

static void gen_SAHF(DisasContext *s, X86DecodedInsn *decode)
{
    /* Keep the retained pre-fix emitter referenced while this overlay exists. */
    (void)gen_SAHF_legacy;

    if (CODE64(s) && !(s->cpuid_ext3_features & CPUID_EXT3_LAHF_LM)) {
        return gen_illegal_opcode(s);
    }

    tcg_gen_shri_tl(s->T0, cpu_regs[R_EAX], 8);
    gen_neg_setcc(s, JCC_O << 1, s->T1);
    tcg_gen_andi_tl(s->T1, s->T1, CC_O);
    tcg_gen_andi_tl(s->T0, s->T0, CC_S | CC_Z | CC_A | CC_P | CC_C);
    tcg_gen_or_tl(s->T0, s->T0, s->T1);

    decode->cc_src = s->T0;
    decode->cc_op = CC_OP_EFLAGS;
}

static inline void gen_fcomi_register_flags(TCGv_env env)
{
    gen_helper_fcomi_ST0_FT0(env);
    tcg_gen_andi_tl(cpu_cc_src, cpu_cc_src,
                    ~(target_ulong)(CC_O | CC_S | CC_A));
}

static inline void gen_fucomi_register_flags(TCGv_env env)
{
    gen_helper_fucomi_ST0_FT0(env);
    tcg_gen_andi_tl(cpu_cc_src, cpu_cc_src,
                    ~(target_ulong)(CC_O | CC_S | CC_A));
}
