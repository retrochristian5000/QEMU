/*
 * Weitek 4167 floating-point coprocessor
 *
 * The 4167 is a memory-mapped coprocessor for 80486-class systems. Its
 * address lines participate in operation decoding, so unaligned MMIO accesses
 * must reach the device without QEMU normalizing the operation address.
 *
 * The programming model is inherited from the object-code-compatible 3167:
 * A15..A10 select the opcode, A9..A7 and A1..A0 select Source1, and A6..A2
 * select Source2/Destination. Source1 == 0 takes its operand from the system
 * data bus. Double-precision registers are even/odd pairs, with the most
 * significant word in the even register.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "qemu/osdep.h"

#include "fpu/softfloat.h"
#include "hw/i386/weitek4167.h"
#include "hw/nvram/fw_cfg.h"
#include "qemu/log.h"
#include "qemu/module.h"

/* Process Context Register fields. */
#define WEITEK_PCR_MOSEL_MASK       0xf0000000U
#define WEITEK_PCR_MODE_MASK        0x0f000000U
#define WEITEK_PCR_RND_MASK         0x0c000000U
#define WEITEK_PCR_IRND             (1U << 25)
#define WEITEK_PCR_FAST             (1U << 24)
#define WEITEK_PCR_EM_MASK          0x00ff0000U
#define WEITEK_PCR_CC_MASK          0x0000ff00U
#define WEITEK_PCR_AE_MASK          0x000000ffU

/* Accumulated exception byte (PCR7..0). */
#define WEITEK_AE_IE                (1U << 0)
#define WEITEK_AE_EE                (1U << 1)
#define WEITEK_AE_ZE                (1U << 2)
#define WEITEK_AE_OE                (1U << 3)
#define WEITEK_AE_UE                (1U << 4)
#define WEITEK_AE_PE                (1U << 5)
#define WEITEK_AE_UOE               (1U << 6)
#define WEITEK_AE_DE                (1U << 7)

/* Exception masks (a set mask bit disables the corresponding interrupt). */
#define WEITEK_EM_IM                (1U << 16)
#define WEITEK_EM_ZM                (1U << 18)
#define WEITEK_EM_OM                (1U << 19)
#define WEITEK_EM_UM                (1U << 20)
#define WEITEK_EM_PM                (1U << 21)
#define WEITEK_EM_UOM               (1U << 22)
#define WEITEK_EM_DM                (1U << 23)

#define WEITEK_NAN32                0x7fffffffU
#define WEITEK_NAN64                UINT64_C(0x7fffffffffffffff)

/* Common instruction opcodes (A15..A10). */
enum {
    WEITEK_OP_ADD_S      = 0x00,
    WEITEK_OP_LOAD_S     = 0x01,
    WEITEK_OP_MUL_S      = 0x02,
    WEITEK_OP_STOR_S     = 0x03,
    WEITEK_OP_SUBR_S     = 0x04,
    WEITEK_OP_DIV_S      = 0x05,
    WEITEK_OP_MULN_S     = 0x06,
    WEITEK_OP_FLOAT_S    = 0x07,
    WEITEK_OP_CMPT_S     = 0x08,
    WEITEK_OP_TSTT_S     = 0x09,
    WEITEK_OP_NEG_S      = 0x0a,
    WEITEK_OP_ABS_S      = 0x0b,
    WEITEK_OP_CMP_S      = 0x0c,
    WEITEK_OP_TST_S      = 0x0d,
    WEITEK_OP_AMUL_S     = 0x0e,
    WEITEK_OP_FIX_S      = 0x0f,
    WEITEK_OP_CVTS_D     = 0x10,
    WEITEK_OP_CVTD_S     = 0x11,
    WEITEK_OP_MAC_S      = 0x12,
    WEITEK_OP_SQRT_S     = 0x13,
    WEITEK_OP_MACD_D     = 0x14,
    WEITEK_OP_SUB_S      = 0x15,

    WEITEK_OP_ADD_D      = 0x20,
    WEITEK_OP_LOAD_D     = 0x21,
    WEITEK_OP_MUL_D      = 0x22,
    WEITEK_OP_STOR_D     = 0x23,
    WEITEK_OP_SUBR_D     = 0x24,
    WEITEK_OP_DIV_D      = 0x25,
    WEITEK_OP_MULN_D     = 0x26,
    WEITEK_OP_FLOAT_D    = 0x27,
    WEITEK_OP_CMPT_D     = 0x28,
    WEITEK_OP_TSTT_D     = 0x29,
    WEITEK_OP_NEG_D      = 0x2a,
    WEITEK_OP_ABS_D      = 0x2b,
    WEITEK_OP_CMP_D      = 0x2c,
    WEITEK_OP_TST_D      = 0x2d,
    WEITEK_OP_AMUL_D     = 0x2e,
    WEITEK_OP_FIX_D      = 0x2f,
    WEITEK_OP_LDCTX      = 0x30,
    WEITEK_OP_STCTX      = 0x31,
    WEITEK_OP_MACD_S     = 0x32,
    WEITEK_OP_SQRT_D     = 0x33,
    WEITEK_OP_PAGE_D     = 0x34,
    WEITEK_OP_SUB_D      = 0x35,
};

struct Weitek4167State {
    SysBusDevice parent_obj;

    MemoryRegion mmio;
    qemu_irq irq;

    /* ws0..ws31; wdN is wsN:wsN+1 for even N. */
    uint32_t regs[32];
    uint32_t pcr;
    float_status fp_status;
};

static hwaddr weitek4167_program_offset(hwaddr offset)
{
    /* A24..A16 are not decoded by the coprocessor programming interface. */
    return offset & WEITEK4167_PROGRAM_MASK;
}

static unsigned weitek4167_opcode(hwaddr offset)
{
    return (offset >> 10) & 0x3f;
}

static unsigned weitek4167_source1(hwaddr offset)
{
    /* Source1 is split between A9..A7 and A1..A0. */
    return (offset & 0x3) | ((offset >> 5) & 0x1c);
}

static unsigned weitek4167_dest(hwaddr offset)
{
    return (offset >> 2) & 0x1f;
}

static bool weitek4167_double_reg_valid(unsigned reg)
{
    return !(reg & 1) && reg < 31;
}

static uint64_t weitek4167_get_double(Weitek4167State *s, unsigned reg)
{
    return ((uint64_t)s->regs[reg] << 32) | s->regs[reg + 1];
}

static void weitek4167_set_double(Weitek4167State *s, unsigned reg,
                                  uint64_t value)
{
    s->regs[reg] = value >> 32;
    s->regs[reg + 1] = value;
}

static void weitek4167_sync_fp_status(Weitek4167State *s)
{
    FloatRoundMode mode;

    switch ((s->pcr & WEITEK_PCR_RND_MASK) >> 26) {
    case 0:
        mode = float_round_nearest_even;
        break;
    case 1:
        mode = float_round_to_zero;
        break;
    case 2:
        mode = float_round_up;
        break;
    default:
        mode = float_round_down;
        break;
    }

    set_float_rounding_mode(mode, &s->fp_status);

    /* The 3167/4167 programming model always operates in Fast Mode. */
    set_flush_inputs_to_zero(true, &s->fp_status);
    set_flush_to_zero(true, &s->fp_status);
    set_float_detect_tininess(false, &s->fp_status);
    set_float_ftz_detection(false, &s->fp_status);

    /* Invalid Weitek operations are normalized below to its all-ones NaN. */
    set_default_nan_mode(true, &s->fp_status);
}

static bool weitek4167_exception_enabled(Weitek4167State *s, uint8_t ae)
{
    if ((ae & WEITEK_AE_IE) && !(s->pcr & WEITEK_EM_IM)) {
        return true;
    }
    if ((ae & WEITEK_AE_ZE) && !(s->pcr & WEITEK_EM_ZM)) {
        return true;
    }
    if ((ae & WEITEK_AE_OE) && !(s->pcr & WEITEK_EM_OM)) {
        return true;
    }
    if ((ae & WEITEK_AE_UE) && !(s->pcr & WEITEK_EM_UM)) {
        return true;
    }
    if ((ae & WEITEK_AE_PE) && !(s->pcr & WEITEK_EM_PM)) {
        return true;
    }
    if ((ae & WEITEK_AE_UOE) && !(s->pcr & WEITEK_EM_UOM)) {
        return true;
    }
    if ((ae & WEITEK_AE_DE) && !(s->pcr & WEITEK_EM_DM)) {
        return true;
    }
    return false;
}

static void weitek4167_update_irq(Weitek4167State *s)
{
    uint8_t ae = s->pcr & WEITEK_PCR_AE_MASK;
    bool level;

    ae &= ~WEITEK_AE_EE;
    level = weitek4167_exception_enabled(s, ae);
    if (level) {
        s->pcr |= WEITEK_AE_EE;
    } else {
        s->pcr &= ~WEITEK_AE_EE;
    }
    qemu_set_irq(s->irq, level);
}

static void weitek4167_raise_ae(Weitek4167State *s, uint8_t flags)
{
    s->pcr |= flags & ~WEITEK_AE_EE;
    weitek4167_update_irq(s);
}

static void weitek4167_begin_fp(Weitek4167State *s)
{
    set_float_exception_flags(0, &s->fp_status);
}

static void weitek4167_finish_fp(Weitek4167State *s)
{
    FloatExceptionFlags sf = get_float_exception_flags(&s->fp_status);
    uint8_t ae = 0;

    if (sf & float_flag_invalid) {
        ae |= WEITEK_AE_IE;
    }
    if (sf & float_flag_divbyzero) {
        ae |= WEITEK_AE_ZE;
    }
    if (sf & float_flag_overflow) {
        ae |= WEITEK_AE_OE;
    }
    if (sf & (float_flag_underflow | float_flag_output_denormal_flushed)) {
        ae |= WEITEK_AE_UE;
    }
    if (sf & float_flag_inexact) {
        ae |= WEITEK_AE_PE;
    }

    if (ae) {
        weitek4167_raise_ae(s, ae);
    }
}

static uint32_t weitek4167_finish_single(Weitek4167State *s, float32 value)
{
    FloatExceptionFlags sf = get_float_exception_flags(&s->fp_status);

    if (sf & float_flag_invalid) {
        value = make_float32(WEITEK_NAN32);
    }
    weitek4167_finish_fp(s);
    return float32_val(value);
}

static uint64_t weitek4167_finish_double(Weitek4167State *s, float64 value)
{
    FloatExceptionFlags sf = get_float_exception_flags(&s->fp_status);

    if (sf & float_flag_invalid) {
        value = make_float64(WEITEK_NAN64);
    }
    weitek4167_finish_fp(s);
    return float64_val(value);
}

static bool weitek4167_source_single(Weitek4167State *s, unsigned src,
                                     uint64_t bus_value, unsigned size,
                                     uint32_t *value)
{
    if (src) {
        *value = s->regs[src];
        return true;
    }

    if (size != 4) {
        qemu_log_mask(LOG_UNIMP,
                      "weitek4167: Source1 bus operand requires 32-bit transfer\n");
        return false;
    }

    *value = bus_value;
    return true;
}

static bool weitek4167_source_double(Weitek4167State *s, unsigned src,
                                     uint64_t bus_value, unsigned size,
                                     uint64_t *value)
{
    if (src) {
        if (!weitek4167_double_reg_valid(src)) {
            qemu_log_mask(LOG_UNIMP,
                          "weitek4167: odd double Source1 register %u\n", src);
            return false;
        }
        *value = weitek4167_get_double(s, src);
        return true;
    }

    if (size != 4) {
        qemu_log_mask(LOG_UNIMP,
                      "weitek4167: double bus operand requires 32-bit transfer\n");
        return false;
    }

    /*
     * The documented double memory-source form is (CPU data, ws1). The first
     * element is the MSW, matching the even/odd register-pair notation.
     */
    *value = ((uint64_t)(uint32_t)bus_value << 32) | s->regs[1];
    return true;
}

static bool weitek4167_defined_opcode(unsigned opcode)
{
    switch (opcode) {
    case WEITEK_OP_ADD_S ... WEITEK_OP_SUB_S:
    case WEITEK_OP_ADD_D ... WEITEK_OP_SUB_D:
        return true;
    default:
        return false;
    }
}

static void weitek4167_unimplemented(Weitek4167State *s, hwaddr offset,
                                     unsigned size, bool is_write)
{
    hwaddr program_offset = weitek4167_program_offset(offset);

    qemu_log_mask(LOG_UNIMP,
                  "weitek4167: unimplemented %s opcode 0x%02x "
                  "(size %u, phys 0x%08" HWADDR_PRIx
                  ", program 0x%04" HWADDR_PRIx ")\n",
                  is_write ? "write" : "read",
                  weitek4167_opcode(program_offset), size,
                  WEITEK4167_MMIO_BASE + offset, program_offset);
}

static void weitek4167_bad_opcode(Weitek4167State *s, hwaddr offset,
                                  unsigned size, bool is_write)
{
    hwaddr program_offset = weitek4167_program_offset(offset);

    qemu_log_mask(LOG_GUEST_ERROR,
                  "weitek4167: undefined opcode 0x%02x on %s "
                  "(size %u, phys 0x%08" HWADDR_PRIx ")\n",
                  weitek4167_opcode(program_offset),
                  is_write ? "write" : "read", size,
                  WEITEK4167_MMIO_BASE + offset);
    weitek4167_raise_ae(s, WEITEK_AE_UOE);
}

static void weitek4167_bad_direction(Weitek4167State *s, hwaddr offset,
                                     unsigned size, bool is_write)
{
    hwaddr program_offset = weitek4167_program_offset(offset);

    qemu_log_mask(LOG_GUEST_ERROR,
                  "weitek4167: invalid bus direction for opcode 0x%02x "
                  "on %s (size %u, phys 0x%08" HWADDR_PRIx ")\n",
                  weitek4167_opcode(program_offset),
                  is_write ? "write" : "read", size,
                  WEITEK4167_MMIO_BASE + offset);
    weitek4167_raise_ae(s, WEITEK_AE_UOE);
}

static void weitek4167_load_context(Weitek4167State *s, uint32_t value)
{
    unsigned mosel = value >> 28;

    switch (mosel) {
    case 0x0:
        /* Update mode, masks, condition codes and accumulated exceptions. */
        s->pcr = value & ~WEITEK_PCR_MOSEL_MASK;
        break;
    case 0xc:
        /* MOSEL=1100 updates EM, CC and AE without changing the mode field. */
        s->pcr = (s->pcr & WEITEK_PCR_MODE_MASK) |
                 (value & (WEITEK_PCR_EM_MASK |
                           WEITEK_PCR_CC_MASK |
                           WEITEK_PCR_AE_MASK));
        break;
    default:
        /* Other MOSEL values are legacy initialization controls. */
        qemu_log_mask(LOG_UNIMP,
                      "weitek4167: unimplemented LDCTX MOSEL=0x%x "
                      "value=0x%08x\n", mosel, value);
        return;
    }

    /* Fast Mode is architecturally fixed on the 3167/4167 interface. */
    s->pcr |= WEITEK_PCR_FAST;

    /* EE is an output/status reflection of INTR, not an accumulated input. */
    s->pcr &= ~WEITEK_AE_EE;
    weitek4167_sync_fp_status(s);
    weitek4167_update_irq(s);
}

static uint64_t weitek4167_read(void *opaque, hwaddr offset, unsigned size)
{
    Weitek4167State *s = opaque;
    hwaddr program_offset = weitek4167_program_offset(offset);
    unsigned opcode = weitek4167_opcode(program_offset);
    unsigned dst = weitek4167_dest(program_offset);

    switch (opcode) {
    case WEITEK_OP_STOR_S:
        /* Store/block-move forms select the register through the T field. */
        return s->regs[dst];
    case WEITEK_OP_STCTX:
        return s->pcr;
    case WEITEK_OP_STOR_D:
    case WEITEK_OP_PAGE_D:
        /* Double stores/page directives need their exact two-cycle protocol. */
        weitek4167_unimplemented(s, offset, size, false);
        return 0;
    default:
        if (weitek4167_defined_opcode(opcode)) {
            /* A read of a non-store opcode is a hardware UOE condition. */
            weitek4167_bad_direction(s, offset, size, false);
        } else {
            weitek4167_bad_opcode(s, offset, size, false);
        }
        return 0;
    }
}

static void weitek4167_write_single(Weitek4167State *s, unsigned opcode,
                                    unsigned src, unsigned dst,
                                    uint64_t bus_value, unsigned size)
{
    uint32_t src_bits;
    float32 srcf, dstf, result;

    if (!weitek4167_source_single(s, src, bus_value, size, &src_bits)) {
        return;
    }

    switch (opcode) {
    case WEITEK_OP_LOAD_S:
        s->regs[dst] = src_bits;
        return;
    case WEITEK_OP_FLOAT_S:
        weitek4167_begin_fp(s);
        result = int32_to_float32((int32_t)src_bits, &s->fp_status);
        s->regs[dst] = weitek4167_finish_single(s, result);
        return;
    case WEITEK_OP_NEG_S:
        weitek4167_begin_fp(s);
        srcf = make_float32(src_bits);
        if (float32_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float32(WEITEK_NAN32);
        } else {
            result = float32_chs(srcf);
        }
        s->regs[dst] = weitek4167_finish_single(s, result);
        return;
    case WEITEK_OP_ABS_S:
        weitek4167_begin_fp(s);
        srcf = make_float32(src_bits);
        if (float32_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float32(WEITEK_NAN32);
        } else {
            result = float32_abs(srcf);
        }
        s->regs[dst] = weitek4167_finish_single(s, result);
        return;
    case WEITEK_OP_FIX_S:
        weitek4167_begin_fp(s);
        srcf = make_float32(src_bits);
        if (s->pcr & WEITEK_PCR_IRND) {
            s->regs[dst] = float32_to_int32_round_to_zero(srcf,
                                                          &s->fp_status);
        } else {
            s->regs[dst] = float32_to_int32(srcf, &s->fp_status);
        }
        weitek4167_finish_fp(s);
        return;
    case WEITEK_OP_CVTD_S: {
        uint64_t out;

        if (!weitek4167_double_reg_valid(dst)) {
            qemu_log_mask(LOG_UNIMP,
                          "weitek4167: odd CVTD.S destination wd%u\n", dst);
            return;
        }
        weitek4167_begin_fp(s);
        srcf = make_float32(src_bits);
        if (float32_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            out = WEITEK_NAN64;
        } else {
            out = weitek4167_finish_double(
                s, float32_to_float64(srcf, &s->fp_status));
            weitek4167_set_double(s, dst, out);
            return;
        }
        weitek4167_finish_fp(s);
        weitek4167_set_double(s, dst, out);
        return;
    }
    case WEITEK_OP_SQRT_S:
        weitek4167_begin_fp(s);
        srcf = make_float32(src_bits);
        if (float32_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float32(WEITEK_NAN32);
        } else {
            result = float32_sqrt(srcf, &s->fp_status);
        }
        s->regs[dst] = weitek4167_finish_single(s, result);
        return;
    default:
        break;
    }

    /* Binary single-precision operations update Source2/Destination. */
    weitek4167_begin_fp(s);
    srcf = make_float32(src_bits);
    dstf = make_float32(s->regs[dst]);

    if (float32_is_any_nan(srcf) || float32_is_any_nan(dstf)) {
        float_raise(float_flag_invalid, &s->fp_status);
        result = make_float32(WEITEK_NAN32);
    } else {
        switch (opcode) {
        case WEITEK_OP_ADD_S:
            result = float32_add(dstf, srcf, &s->fp_status);
            break;
        case WEITEK_OP_MUL_S:
            result = float32_mul(dstf, srcf, &s->fp_status);
            break;
        case WEITEK_OP_SUBR_S:
            result = float32_sub(srcf, dstf, &s->fp_status);
            break;
        case WEITEK_OP_DIV_S:
            result = float32_div(srcf, dstf, &s->fp_status);
            break;
        case WEITEK_OP_MULN_S:
            result = float32_chs(float32_mul(dstf, srcf, &s->fp_status));
            break;
        case WEITEK_OP_AMUL_S:
            result = float32_abs(float32_mul(dstf, srcf, &s->fp_status));
            break;
        case WEITEK_OP_SUB_S:
            result = float32_sub(dstf, srcf, &s->fp_status);
            break;
        default:
            return;
        }
    }

    s->regs[dst] = weitek4167_finish_single(s, result);
}

static void weitek4167_write_double(Weitek4167State *s, unsigned opcode,
                                    unsigned src, unsigned dst,
                                    uint64_t bus_value, unsigned size)
{
    uint64_t src_bits, dst_bits;
    float64 srcf, dstf, result;

    if (!weitek4167_double_reg_valid(dst)) {
        qemu_log_mask(LOG_UNIMP,
                      "weitek4167: odd double destination wd%u\n", dst);
        return;
    }
    if (!weitek4167_source_double(s, src, bus_value, size, &src_bits)) {
        return;
    }

    switch (opcode) {
    case WEITEK_OP_LOAD_D:
        weitek4167_set_double(s, dst, src_bits);
        return;
    case WEITEK_OP_NEG_D:
        weitek4167_begin_fp(s);
        srcf = make_float64(src_bits);
        if (float64_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float64(WEITEK_NAN64);
        } else {
            result = float64_chs(srcf);
        }
        weitek4167_set_double(s, dst,
                             weitek4167_finish_double(s, result));
        return;
    case WEITEK_OP_ABS_D:
        weitek4167_begin_fp(s);
        srcf = make_float64(src_bits);
        if (float64_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float64(WEITEK_NAN64);
        } else {
            result = float64_abs(srcf);
        }
        weitek4167_set_double(s, dst,
                             weitek4167_finish_double(s, result));
        return;
    case WEITEK_OP_SQRT_D:
        weitek4167_begin_fp(s);
        srcf = make_float64(src_bits);
        if (float64_is_any_nan(srcf)) {
            float_raise(float_flag_invalid, &s->fp_status);
            result = make_float64(WEITEK_NAN64);
        } else {
            result = float64_sqrt(srcf, &s->fp_status);
        }
        weitek4167_set_double(s, dst,
                             weitek4167_finish_double(s, result));
        return;
    default:
        break;
    }

    dst_bits = weitek4167_get_double(s, dst);
    weitek4167_begin_fp(s);
    srcf = make_float64(src_bits);
    dstf = make_float64(dst_bits);

    if (float64_is_any_nan(srcf) || float64_is_any_nan(dstf)) {
        float_raise(float_flag_invalid, &s->fp_status);
        result = make_float64(WEITEK_NAN64);
    } else {
        switch (opcode) {
        case WEITEK_OP_ADD_D:
            result = float64_add(dstf, srcf, &s->fp_status);
            break;
        case WEITEK_OP_MUL_D:
            result = float64_mul(dstf, srcf, &s->fp_status);
            break;
        case WEITEK_OP_SUBR_D:
            result = float64_sub(srcf, dstf, &s->fp_status);
            break;
        case WEITEK_OP_DIV_D:
            result = float64_div(srcf, dstf, &s->fp_status);
            break;
        case WEITEK_OP_MULN_D:
            result = float64_chs(float64_mul(dstf, srcf, &s->fp_status));
            break;
        case WEITEK_OP_AMUL_D:
            result = float64_abs(float64_mul(dstf, srcf, &s->fp_status));
            break;
        case WEITEK_OP_SUB_D:
            result = float64_sub(dstf, srcf, &s->fp_status);
            break;
        default:
            return;
        }
    }

    weitek4167_set_double(s, dst, weitek4167_finish_double(s, result));
}

static void weitek4167_mac_s(Weitek4167State *s, unsigned src,
                             unsigned src2, uint64_t bus_value, unsigned size)
{
    uint32_t src_bits;
    float32 a, b, acc, result;

    if (!weitek4167_source_single(s, src, bus_value, size, &src_bits)) {
        return;
    }

    a = make_float32(src_bits);
    b = make_float32(s->regs[src2]);
    acc = make_float32(s->regs[2]);
    weitek4167_begin_fp(s);

    if (float32_is_any_nan(a) || float32_is_any_nan(b) ||
        float32_is_any_nan(acc)) {
        float_raise(float_flag_invalid, &s->fp_status);
        result = make_float32(WEITEK_NAN32);
    } else {
        /*
         * The hardware description specifies a multiply followed by an add to
         * ws2, but does not expose the internal intermediate rounding point.
         * SoftFloat muladd provides the closest one-round functional model;
         * bit-exact pipeline rounding remains a separate conformance audit.
         */
        result = float32_muladd(a, b, acc, 0, &s->fp_status);
    }

    s->regs[2] = weitek4167_finish_single(s, result);
}

static void weitek4167_macd_s(Weitek4167State *s, unsigned src,
                              unsigned src2, uint64_t bus_value, unsigned size)
{
    uint32_t src_bits;
    float32 a32, b32;
    float64 a, b, acc, result;

    if (!weitek4167_source_single(s, src, bus_value, size, &src_bits)) {
        return;
    }

    a32 = make_float32(src_bits);
    b32 = make_float32(s->regs[src2]);
    acc = make_float64(weitek4167_get_double(s, 2));
    weitek4167_begin_fp(s);

    if (float32_is_any_nan(a32) || float32_is_any_nan(b32) ||
        float64_is_any_nan(acc)) {
        float_raise(float_flag_invalid, &s->fp_status);
        result = make_float64(WEITEK_NAN64);
    } else {
        a = float32_to_float64(a32, &s->fp_status);
        b = float32_to_float64(b32, &s->fp_status);
        result = float64_muladd(a, b, acc, 0, &s->fp_status);
    }

    weitek4167_set_double(s, 2, weitek4167_finish_double(s, result));
}

static void weitek4167_macd_d(Weitek4167State *s, unsigned src,
                              unsigned src2, uint64_t bus_value, unsigned size)
{
    uint64_t src_bits;
    float64 a, b, acc, result;

    if (!weitek4167_double_reg_valid(src2)) {
        qemu_log_mask(LOG_UNIMP,
                      "weitek4167: odd MACD.D Source2 register wd%u\n", src2);
        return;
    }
    if (!weitek4167_source_double(s, src, bus_value, size, &src_bits)) {
        return;
    }

    a = make_float64(src_bits);
    b = make_float64(weitek4167_get_double(s, src2));
    acc = make_float64(weitek4167_get_double(s, 2));
    weitek4167_begin_fp(s);

    if (float64_is_any_nan(a) || float64_is_any_nan(b) ||
        float64_is_any_nan(acc)) {
        float_raise(float_flag_invalid, &s->fp_status);
        result = make_float64(WEITEK_NAN64);
    } else {
        result = float64_muladd(a, b, acc, 0, &s->fp_status);
    }

    weitek4167_set_double(s, 2, weitek4167_finish_double(s, result));
}

static void weitek4167_write(void *opaque, hwaddr offset,
                             uint64_t value, unsigned size)
{
    Weitek4167State *s = opaque;
    hwaddr program_offset = weitek4167_program_offset(offset);
    unsigned opcode = weitek4167_opcode(program_offset);
    unsigned src = weitek4167_source1(program_offset);
    unsigned dst = weitek4167_dest(program_offset);
    uint32_t src_bits;
    uint64_t src64;
    float64 srcd;
    float32 outs;

    switch (opcode) {
    case WEITEK_OP_STOR_S:
    case WEITEK_OP_STOR_D:
    case WEITEK_OP_STCTX:
        weitek4167_bad_direction(s, offset, size, true);
        return;
    case WEITEK_OP_LDCTX:
        if (size != 4) {
            weitek4167_unimplemented(s, offset, size, true);
            return;
        }
        weitek4167_load_context(s, value);
        return;

    case WEITEK_OP_ADD_S:
    case WEITEK_OP_LOAD_S:
    case WEITEK_OP_MUL_S:
    case WEITEK_OP_SUBR_S:
    case WEITEK_OP_DIV_S:
    case WEITEK_OP_MULN_S:
    case WEITEK_OP_FLOAT_S:
    case WEITEK_OP_NEG_S:
    case WEITEK_OP_ABS_S:
    case WEITEK_OP_AMUL_S:
    case WEITEK_OP_FIX_S:
    case WEITEK_OP_CVTD_S:
    case WEITEK_OP_SQRT_S:
    case WEITEK_OP_SUB_S:
        weitek4167_write_single(s, opcode, src, dst, value, size);
        return;

    case WEITEK_OP_MAC_S:
        weitek4167_mac_s(s, src, dst, value, size);
        return;
    case WEITEK_OP_MACD_S:
        weitek4167_macd_s(s, src, dst, value, size);
        return;
    case WEITEK_OP_MACD_D:
        weitek4167_macd_d(s, src, dst, value, size);
        return;

    case WEITEK_OP_CVTS_D:
        if (!weitek4167_source_double(s, src, value, size, &src64)) {
            return;
        }
        weitek4167_begin_fp(s);
        srcd = make_float64(src64);
        if (float64_is_any_nan(srcd)) {
            float_raise(float_flag_invalid, &s->fp_status);
            outs = make_float32(WEITEK_NAN32);
        } else {
            outs = float64_to_float32(srcd, &s->fp_status);
        }
        s->regs[dst] = weitek4167_finish_single(s, outs);
        return;

    case WEITEK_OP_ADD_D:
    case WEITEK_OP_LOAD_D:
    case WEITEK_OP_MUL_D:
    case WEITEK_OP_SUBR_D:
    case WEITEK_OP_DIV_D:
    case WEITEK_OP_MULN_D:
    case WEITEK_OP_NEG_D:
    case WEITEK_OP_ABS_D:
    case WEITEK_OP_AMUL_D:
    case WEITEK_OP_SQRT_D:
    case WEITEK_OP_SUB_D:
        weitek4167_write_double(s, opcode, src, dst, value, size);
        return;

    case WEITEK_OP_FLOAT_D:
        if (!weitek4167_source_single(s, src, value, size, &src_bits)) {
            return;
        }
        if (!weitek4167_double_reg_valid(dst)) {
            weitek4167_unimplemented(s, offset, size, true);
            return;
        }
        weitek4167_begin_fp(s);
        src64 = float64_val(int32_to_float64((int32_t)src_bits,
                                             &s->fp_status));
        weitek4167_finish_fp(s);
        weitek4167_set_double(s, dst, src64);
        return;

    case WEITEK_OP_FIX_D:
        if (!weitek4167_source_double(s, src, value, size, &src64)) {
            return;
        }
        weitek4167_begin_fp(s);
        srcd = make_float64(src64);
        if (s->pcr & WEITEK_PCR_IRND) {
            s->regs[dst] = float64_to_int32_round_to_zero(srcd,
                                                          &s->fp_status);
        } else {
            s->regs[dst] = float64_to_int32(srcd, &s->fp_status);
        }
        weitek4167_finish_fp(s);
        return;

    case WEITEK_OP_CMPT_S:
    case WEITEK_OP_TSTT_S:
    case WEITEK_OP_CMP_S:
    case WEITEK_OP_TST_S:
    case WEITEK_OP_CMPT_D:
    case WEITEK_OP_TSTT_D:
    case WEITEK_OP_CMP_D:
    case WEITEK_OP_TST_D:
    case WEITEK_OP_PAGE_D:
        weitek4167_unimplemented(s, offset, size, true);
        return;

    default:
        weitek4167_bad_opcode(s, offset, size, true);
        return;
    }
}

static const MemoryRegionOps weitek4167_ops = {
    .read = weitek4167_read,
    .write = weitek4167_write,
    .endianness = DEVICE_LITTLE_ENDIAN,
    .valid = {
        /* 80486 byte-enable signals select the active data lanes. */
        .min_access_size = 1,
        .max_access_size = 4,
        .unaligned = true,
    },
    .impl = {
        .min_access_size = 1,
        .max_access_size = 4,
        .unaligned = true,
    },
};

static void weitek4167_reset(DeviceState *dev)
{
    Weitek4167State *s = WEITEK4167(dev);

    /*
     * The hardware documentation does not define register-file reset values.
     * QEMU normalizes that architecturally-undefined state to zero so reset is
     * deterministic; guest software must still initialize any state it uses.
     * FAST is the one documented PCR mode bit that must always read as one.
     */
    memset(s->regs, 0, sizeof(s->regs));
    s->pcr = WEITEK_PCR_FAST;
    memset(&s->fp_status, 0, sizeof(s->fp_status));
    weitek4167_sync_fp_status(s);
    qemu_set_irq(s->irq, 0);
}

static void weitek4167_realize(DeviceState *dev, Error **errp)
{
    Weitek4167State *s = WEITEK4167(dev);
    FWCfgState *fw_cfg = fw_cfg_find();

    s->pcr |= WEITEK_PCR_FAST;
    weitek4167_sync_fp_status(s);

    /* PRES# is represented to the PC firmware by a fw_cfg presence file. */
    if (fw_cfg) {
        uint32_t *present = g_new(uint32_t, 1);

        *present = cpu_to_le32(1);
        fw_cfg_add_file(fw_cfg, "etc/weitek4167", present, sizeof(*present));
    }
}

static void weitek4167_init(Object *obj)
{
    Weitek4167State *s = WEITEK4167(obj);

    /* M/IO# is memory-only: the 4167 has no legacy port-I/O register block. */
    memory_region_init_io(&s->mmio, obj, &weitek4167_ops, s,
                          TYPE_WEITEK4167, WEITEK4167_MMIO_SIZE);
    sysbus_init_mmio(SYS_BUS_DEVICE(obj), &s->mmio);

    /* INTR is connected by the PC board to the AT-compatible IRQ13 path. */
    sysbus_init_irq(SYS_BUS_DEVICE(obj), &s->irq);
}

static void weitek4167_class_init(ObjectClass *klass, const void *data)
{
    DeviceClass *dc = DEVICE_CLASS(klass);

    dc->realize = weitek4167_realize;
    device_class_set_legacy_reset(dc, weitek4167_reset);
    set_bit(DEVICE_CATEGORY_MISC, dc->categories);

    /* The board must map the decode aperture and wire INTR correctly. */
    dc->user_creatable = false;
}

static const TypeInfo weitek4167_info = {
    .name = TYPE_WEITEK4167,
    .parent = TYPE_SYS_BUS_DEVICE,
    .instance_size = sizeof(Weitek4167State),
    .instance_init = weitek4167_init,
    .class_init = weitek4167_class_init,
};

static void weitek4167_register_types(void)
{
    type_register_static(&weitek4167_info);
}

type_init(weitek4167_register_types)
