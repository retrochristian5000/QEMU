/*
 * WHP x87 transcendental helpers
 *
 * Keep FSIN, FCOS and FPTAN in QEMU floatx80 arithmetic instead of
 * converting the guest operand to host double and delegating to libm.
 *
 * The transcendental implementation is the FPSP-derived floatx80 code used
 * by QEMU's m68k FPU.  x87-specific input validity, C2 range handling,
 * exception propagation and FPTAN stack semantics remain here.
 */

#include "qemu/osdep.h"
#include "cpu.h"
#include "exec/helper-proto.h"
#include "fpu/softfloat.h"
#include "../../m68k/softfloat.h"

#define X87_FPU_C2          0x0400
#define X87_TRIG_MAX_EXP    0x403e
#define X87_TRIG_MAX_SIG    UINT64_C(0x8000000000000000)

#define X87_FPUS_IE         (1 << 0)
#define X87_FPUS_DE         (1 << 1)
#define X87_FPUS_ZE         (1 << 2)
#define X87_FPUS_OE         (1 << 3)
#define X87_FPUS_UE         (1 << 4)
#define X87_FPUS_PE         (1 << 5)
#define X87_FPUS_SE         (1 << 7)
#define X87_FPUS_B          (1 << 15)
#define X87_FPUC_EM         0x3f

static inline floatx80 *x87_st0(CPUX86State *env)
{
    return &env->fpregs[env->fpstt].d;
}

static inline void x87_push(CPUX86State *env)
{
    env->fpstt = (env->fpstt - 1) & 7;
    env->fptags[env->fpstt] = 0;
}

static int x87_save_exception_flags(CPUX86State *env)
{
    int old_flags = get_float_exception_flags(&env->fp_status);

    set_float_exception_flags(0, &env->fp_status);
    return old_flags;
}

static void x87_set_exception(CPUX86State *env, int mask)
{
    env->fpus |= mask;
    if (env->fpus & (~env->fpuc & X87_FPUC_EM)) {
        env->fpus |= X87_FPUS_SE | X87_FPUS_B;
    }
}

static void x87_merge_exception_flags(CPUX86State *env, int old_flags)
{
    int new_flags = get_float_exception_flags(&env->fp_status);

    float_raise(old_flags, &env->fp_status);
    x87_set_exception(env,
                      ((new_flags & float_flag_invalid ? X87_FPUS_IE : 0) |
                       (new_flags & float_flag_divbyzero ? X87_FPUS_ZE : 0) |
                       (new_flags & float_flag_overflow ? X87_FPUS_OE : 0) |
                       (new_flags & float_flag_underflow ? X87_FPUS_UE : 0) |
                       (new_flags & float_flag_inexact ? X87_FPUS_PE : 0) |
                       (new_flags & float_flag_input_denormal_used ?
                        X87_FPUS_DE : 0)));
}

/*
 * Intel defines C2 for these instructions when the finite input is outside
 * the supported reduction range.  The legacy QEMU helpers use a strict
 * comparison with 2^63, so +/-2^63 itself remains an accepted input.
 */
static bool x87_trig_out_of_range(floatx80 a)
{
    int32_t exp = extractFloatx80Exp(a);
    uint64_t sig = extractFloatx80Frac(a);

    if (exp == 0x7fff) {
        return false;
    }
    return exp > X87_TRIG_MAX_EXP ||
           (exp == X87_TRIG_MAX_EXP && sig > X87_TRIG_MAX_SIG);
}

static bool x87_trig_reject_invalid_encoding(CPUX86State *env)
{
    floatx80 *st0 = x87_st0(env);
    int old_flags;

    if (!floatx80_invalid_encoding(*st0, &env->fp_status)) {
        return false;
    }

    old_flags = x87_save_exception_flags(env);
    float_raise(float_flag_invalid, &env->fp_status);
    *st0 = floatx80_default_nan(&env->fp_status);
    x87_merge_exception_flags(env, old_flags);
    env->fpus &= ~X87_FPU_C2;
    return true;
}

static bool x87_trig_prepare(CPUX86State *env)
{
    if (x87_trig_reject_invalid_encoding(env)) {
        return false;
    }

    if (x87_trig_out_of_range(*x87_st0(env))) {
        env->fpus |= X87_FPU_C2;
        return false;
    }

    return true;
}

void helper_fsin_whp(CPUX86State *env)
{
    floatx80 *st0 = x87_st0(env);
    int old_flags;

    if (!x87_trig_prepare(env)) {
        return;
    }

    old_flags = x87_save_exception_flags(env);
    *st0 = floatx80_sin(*st0, &env->fp_status);
    x87_merge_exception_flags(env, old_flags);
    env->fpus &= ~X87_FPU_C2;
}

void helper_fcos_whp(CPUX86State *env)
{
    floatx80 *st0 = x87_st0(env);
    int old_flags;

    if (!x87_trig_prepare(env)) {
        return;
    }

    old_flags = x87_save_exception_flags(env);
    *st0 = floatx80_cos(*st0, &env->fp_status);
    x87_merge_exception_flags(env, old_flags);
    env->fpus &= ~X87_FPU_C2;
}

void helper_fptan_whp(CPUX86State *env)
{
    floatx80 result;
    int old_flags;

    if (!x87_trig_prepare(env)) {
        return;
    }

    old_flags = x87_save_exception_flags(env);
    result = floatx80_tan(*x87_st0(env), &env->fp_status);
    x87_merge_exception_flags(env, old_flags);

    *x87_st0(env) = result;
    x87_push(env);
    *x87_st0(env) = floatx80_one;
    env->fpus &= ~X87_FPU_C2;
}
