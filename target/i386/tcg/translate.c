/*
 * Select the i386 translator at build time.
 * Keep original 16-bit x86 decode costs out of generic i386 builds.
 */
#ifdef TARGET_X86_16BIT
#include "translate-original-x86.c.inc"
#else
#include "translate-generic.c.inc"
#endif
