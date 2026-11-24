/*
 * CPU-side Metal upload instrumentation for ThreadSanitizer.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_COCOA_METAL_TSAN_H
#define QEMU_COCOA_METAL_TSAN_H

#include <stddef.h>
#include <stdint.h>

#ifdef QEMU_SANITIZE_THREAD
/* Existing compiler-rt instrumentation ABI; older SDK headers omit it. */
void __tsan_read_range(void *addr, unsigned long size);
#endif

static inline void qemu_cocoa_metal_tsan_read_rows(const uint8_t *bytes,
                                                  size_t row_bytes,
                                                  size_t stride,
                                                  size_t rows)
{
#ifdef QEMU_SANITIZE_THREAD
    if (!rows || !row_bytes) {
        return;
    }
    if (row_bytes == stride) {
        __tsan_read_range((void *)bytes, row_bytes * rows);
        return;
    }
    for (size_t row = 0; row < rows; row++) {
        __tsan_read_range((void *)(bytes + row * stride), row_bytes);
    }
#else
    (void)bytes;
    (void)row_bytes;
    (void)stride;
    (void)rows;
#endif
}

#endif /* QEMU_COCOA_METAL_TSAN_H */
