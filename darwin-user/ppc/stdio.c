/*
 * Bounded, host-independent Darwin PPC read(0) helper.
 * The caller is responsible for forwarding the result through the actual
 * guest PPC syscall return ABI; no QEMU target is exposed by this code.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "darwin-user/ppc/stdio.h"

#include <limits.h>

static void stdin_fail(QemuDarwinPpcStdinResult *result, int guest_errno)
{
    result->error = true;
    result->value = (uint64_t)guest_errno;
}

bool qemu_darwin_ppc_stdin_read(unsigned int guest_bits, uint64_t r0,
                                uint64_t r3, uint64_t r4, uint64_t r5,
                                const QemuDarwinPpcStdinOps *ops,
                                void *opaque, QemuDarwinPpcStdinResult *result)
{
    uint64_t address, count, limit;
    size_t request, received = 0;
    int guest_errno = QEMU_DARWIN_PPC_EIO;
    uint8_t buffer[QEMU_DARWIN_PPC_READ_CHUNK];

    if (result == NULL || ops == NULL || ops->guest_writable == NULL ||
        ops->guest_write == NULL || ops->host_read == NULL) {
        return false;
    }
    if (guest_bits != 32 && guest_bits != 64) {
        stdin_fail(result, QEMU_DARWIN_PPC_EINVAL);
        return true;
    }
    limit = guest_bits == 32 ? UINT32_MAX : UINT64_MAX;
    r0 &= limit;
    r3 &= limit;
    if (r0 != QEMU_DARWIN_PPC_BSD_READ || r3 != QEMU_DARWIN_PPC_STDIN_FD) {
        return false;
    }
    address = r4 & limit;
    count = r5 & limit;
    request = count > sizeof(buffer) ? sizeof(buffer) : (size_t)count;

    if (request != 0 &&
        (address > limit - (request - 1) ||
         !ops->guest_writable(opaque, address, request))) {
        stdin_fail(result, QEMU_DARWIN_PPC_EFAULT);
        return true;
    }
    /* Zero-length read still calls the fd backend so a closed descriptor can
     * report an error; a null buffer need not pass guest access validation.
     */
    if (!ops->host_read(opaque, 0, buffer, request, &received, &guest_errno)) {
        stdin_fail(result, guest_errno > 0 ? guest_errno : QEMU_DARWIN_PPC_EIO);
        return true;
    }
    if (received > request) {
        stdin_fail(result, QEMU_DARWIN_PPC_EIO);
        return true;
    }
    if (received != 0 &&
        !ops->guest_write(opaque, address, buffer, received)) {
        stdin_fail(result, QEMU_DARWIN_PPC_EFAULT);
        return true;
    }
    result->error = false;
    result->value = received;
    return true;
}
