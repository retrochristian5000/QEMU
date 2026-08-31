/*
 * i386 architectural flag-register regression tests.
 *
 * Keep these tests bare-metal so they exercise qemu-system-i386 TCG rather
 * than a host kernel's signal/context machinery.
 */

typedef unsigned int u32;

#define X86_CF (1u << 0)
#define X86_PF (1u << 2)
#define X86_AF (1u << 4)
#define X86_ZF (1u << 6)
#define X86_SF (1u << 7)
#define X86_OF (1u << 11)
#define X86_ARITH_FLAGS (X86_CF | X86_PF | X86_AF | X86_ZF | X86_SF | X86_OF)

static int test_sahf_lazy_flags(void)
{
    u32 flags;

    asm volatile(
        "xorl %%eax, %%eax\n\t"
        "movb $0x81, %%ah\n\t"
        "sahf\n\t"
        "pushfl\n\t"
        "popl %0\n\t"
        : "=r" (flags)
        :
        : "eax", "cc");

    return (flags & X86_ARITH_FLAGS) == (X86_SF | X86_CF) ? 0 : 1;
}

static int test_fcomi_clears_status_flags(void)
{
    u32 flags;

    asm volatile(
        "fninit\n\t"
        "fld1\n\t"
        "fld1\n\t"
        "movl $0x7fffffff, %%eax\n\t"
        "addl $1, %%eax\n\t"
        /* FCOMI ST(0), ST(1): equal, so only ZF is set. */
        ".byte 0xdb, 0xf1\n\t"
        "pushfl\n\t"
        "popl %0\n\t"
        : "=r" (flags)
        :
        : "eax", "cc");

    return (flags & X86_ARITH_FLAGS) == X86_ZF ? 0 : 2;
}

static int test_fucomi_clears_status_flags(void)
{
    u32 flags;

    asm volatile(
        "fninit\n\t"
        "fld1\n\t"
        "fld1\n\t"
        "movl $0x7fffffff, %%eax\n\t"
        "addl $1, %%eax\n\t"
        /* FUCOMI ST(0), ST(1): equal, so only ZF is set. */
        ".byte 0xdb, 0xe9\n\t"
        "pushfl\n\t"
        "popl %0\n\t"
        : "=r" (flags)
        :
        : "eax", "cc");

    return (flags & X86_ARITH_FLAGS) == X86_ZF ? 0 : 3;
}

int main(void)
{
    int ret;

    ret = test_sahf_lazy_flags();
    if (ret) {
        return ret;
    }

    ret = test_fcomi_clears_status_flags();
    if (ret) {
        return ret;
    }

    return test_fucomi_clears_status_flags();
}
