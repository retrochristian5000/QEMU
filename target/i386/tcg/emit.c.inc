/*
 * Select i386 instruction emission at build time.
 * Original 8086/8088 PUSH semantics belong only to the dedicated x86 target.
 */
#define gen_SAHF gen_SAHF_legacy
#ifdef TARGET_X86_16BIT
#include "emit-original-x86.c.inc"
#else
#include "emit-generic.c.inc"
#endif
#undef gen_SAHF

#include "emit-register-flags.c.inc"

/*
 * The x87 translator follows this emitter include in both translation units.
 * Redirect only the compare helpers whose arithmetic flags need masking.
 */
#define gen_helper_fcomi_ST0_FT0 gen_fcomi_register_flags
#define gen_helper_fucomi_ST0_FT0 gen_fucomi_register_flags
