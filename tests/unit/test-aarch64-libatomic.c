/*
 * SPDX-License-Identifier: GPL-2.0-or-later
 * Standalone AArch64 libatomic ABI smoke test.
 *
 * Keep these objects private to the runtime: do not mix library operations
 * with QEMU guest-memory atomics, even when the runtime reports lock freedom.
 */

#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>

typedef __uint128_t AtomicValue;

/* Alternate C names force calls to the actual runtime entry points. */
extern AtomicValue runtime_load(const volatile void *, int)
    __asm__("__atomic_load_16");
extern void runtime_store(volatile void *, AtomicValue, int)
    __asm__("__atomic_store_16");
extern bool runtime_cas(volatile void *, void *, AtomicValue, int, int)
    __asm__("__atomic_compare_exchange_16");

int main(void)
{
    _Alignas(16) AtomicValue value;
    AtomicValue first = ((AtomicValue)UINT64_C(0x123456789abcdef0) << 64) |
                        UINT64_C(0xfedcba9876543210);
    AtomicValue second = ~first;
    AtomicValue expected;

    runtime_store(&value, first, __ATOMIC_SEQ_CST);
    if (runtime_load(&value, __ATOMIC_SEQ_CST) != first) {
        fputs("libatomic: 128-bit load/store mismatch\n", stderr);
        return 1;
    }

    expected = first;
    if (!runtime_cas(&value, &expected, second, __ATOMIC_SEQ_CST,
                     __ATOMIC_SEQ_CST) ||
        runtime_load(&value, __ATOMIC_SEQ_CST) != second) {
        fputs("libatomic: 128-bit compare-exchange success mismatch\n",
              stderr);
        return 1;
    }

    expected = first;
    if (runtime_cas(&value, &expected, first, __ATOMIC_SEQ_CST,
                    __ATOMIC_SEQ_CST) ||
        expected != second ||
        runtime_load(&value, __ATOMIC_SEQ_CST) != second) {
        fputs("libatomic: 128-bit compare-exchange failure mismatch\n",
              stderr);
        return 1;
    }

    return 0;
}
