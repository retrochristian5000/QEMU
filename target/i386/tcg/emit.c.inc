/*
 * Select i386 instruction emission at build time.
 * Original 8086/8088 PUSH semantics belong only to the dedicated x86 target.
 */
#ifdef TARGET_X86_16BIT
#include "emit-original-x86.c.inc"
#else
#include "emit-generic.c.inc"
#endif
