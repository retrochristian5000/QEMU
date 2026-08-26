/*
 * Select the i386 decoder at build time.
 * Original 16-bit restrictions belong only to the dedicated x86 target.
 */
#ifdef TARGET_X86_16BIT
#include "decode-original-x86.c.inc"
#else
#include "decode-generic.c.inc"
#endif
