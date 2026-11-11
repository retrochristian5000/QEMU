/*
 * Darwin PowerPC BSD stdin translation boundary.
 * Historical ABI: r0 = BSD syscall 3, r3 = fd, r4 = buffer, r5 = length.
 * This standalone interface is not a live Darwin-user syscall dispatcher.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_DARWIN_PPC_STDIO_H
#define QEMU_DARWIN_PPC_STDIO_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define QEMU_DARWIN_PPC_BSD_READ 3U
#define QEMU_DARWIN_PPC_STDIN_FD 0U
#define QEMU_DARWIN_PPC_READ_CHUNK 4096U

/* Darwin guest errno values, not host errno numbers. */
#define QEMU_DARWIN_PPC_EINTR 4
#define QEMU_DARWIN_PPC_EIO 5
#define QEMU_DARWIN_PPC_EFAULT 14
#define QEMU_DARWIN_PPC_EINVAL 22

typedef struct QemuDarwinPpcStdinResult {
    uint64_t value;          /* byte count on success, guest errno on failure */
    bool error;              /* PPC syscall return convention handled later */
} QemuDarwinPpcStdinResult;

typedef struct QemuDarwinPpcStdinOps {
    /* Access validation must not read or consume host stdin. */
    bool (*guest_writable)(void *opaque, uint64_t address, size_t length);
    bool (*guest_write)(void *opaque, uint64_t address,
                        const uint8_t *data, size_t length);
    /* Translate host errors into Darwin errno; never expose host errno. */
    bool (*host_read)(void *opaque, int fd, uint8_t *buffer, size_t requested,
                      size_t *received, int *darwin_errno);
} QemuDarwinPpcStdinOps;

/* Return false if this is not the supported read(0, ...) operation.
 * A true return supplies a result even on EFAULT or a host I/O error.
 * Registers are unsigned containers: PPC32 uses their low 32 bits.
 */
bool qemu_darwin_ppc_stdin_read(unsigned int guest_bits, uint64_t r0,
                                uint64_t r3, uint64_t r4, uint64_t r5,
                                const QemuDarwinPpcStdinOps *ops,
                                void *opaque, QemuDarwinPpcStdinResult *result);

#endif
