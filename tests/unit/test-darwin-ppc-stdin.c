/*
 * PowerPC Darwin BSD read(0) regression: guest vs host address isolation,
 * partial reads, EOF and host-to-Darwin errno handling.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "darwin-user/ppc/stdio.h"
#include <assert.h>
#include <string.h>
#include <unistd.h>

typedef struct Fixture {
    uint8_t guest[8192];
    uint64_t base;
    int fd;
    unsigned int checks, reads, writes;
    int forced_error;
    bool invalid;
} Fixture;

static bool access_guest(void *opaque, uint64_t address, size_t len)
{
    Fixture *f = opaque;
    f->checks++;
    return !f->invalid && address >= f->base &&
           (address - f->base) <= sizeof(f->guest) &&
           len <= sizeof(f->guest) - (size_t)(address - f->base);
}

static bool copy_guest(void *opaque, uint64_t address,
                       const uint8_t *data, size_t len)
{
    Fixture *f = opaque;
    f->writes++;
    if (!access_guest(opaque, address, len)) {
        return false;
    }
    memcpy(f->guest + (size_t)(address - f->base), data, len);
    return true;
}

static bool read_host(void *opaque, int fd, uint8_t *buffer,
                      size_t len, size_t *received, int *darwin_errno)
{
    Fixture *f = opaque;
    ssize_t n;
    f->reads++;
    assert(fd == 0);
    if (f->forced_error) {
        *darwin_errno = f->forced_error;
        return false;
    }
    n = read(f->fd, buffer, len);
    if (n < 0) {
        *darwin_errno = QEMU_DARWIN_PPC_EIO;
        return false;
    }
    *received = (size_t)n;
    return true;
}

int main(void)
{
    const QemuDarwinPpcStdinOps ops = { access_guest, copy_guest, read_host };
    QemuDarwinPpcStdinResult result = { 0 };
    Fixture f = { .base = 0x1000 };
    int pipefd[2];
    assert(pipe(pipefd) == 0);
    f.fd = pipefd[0];
    assert(write(pipefd[1], "hello", 5) == 5);

    /* Other syscall classes and file descriptors are not intercepted. */
    assert(!qemu_darwin_ppc_stdin_read(32, 4, 0, 0x1000, 3, &ops, &f, &result));
    assert(!qemu_darwin_ppc_stdin_read(32, 0xffffffffu, 0, 0x1000, 3, &ops, &f, &result));
    assert(!qemu_darwin_ppc_stdin_read(32, 3, 1, 0x1000, 3, &ops, &f, &result));
    assert(f.reads == 0);

    /* EFAULT must not consume input on an invalid or wrapping address. */
    assert(qemu_darwin_ppc_stdin_read(32, 3, 0, 0xfffffffeu, 4, &ops, &f, &result));
    assert(result.error && result.value == QEMU_DARWIN_PPC_EFAULT && f.reads == 0);
    f.invalid = true;
    assert(qemu_darwin_ppc_stdin_read(32, 3, 0, 0x1000, 4, &ops, &f, &result));
    assert(result.error && result.value == QEMU_DARWIN_PPC_EFAULT && f.reads == 0);
    f.invalid = false;

    assert(qemu_darwin_ppc_stdin_read(32, 3, 0, 0x1000, 5, &ops, &f, &result));
    assert(!result.error && result.value == 5 && memcmp(f.guest, "hello", 5) == 0);
    assert(f.reads == 1);

    /* A PPC64 pointer must not be truncated to the PPC32 address range. */
    f.base = UINT64_C(0x100000000);
    assert(write(pipefd[1], "G5!", 3) == 3);
    assert(qemu_darwin_ppc_stdin_read(64, 3, 0, f.base, 3, &ops, &f, &result));
    assert(!result.error && result.value == 3 && memcmp(f.guest, "G5!", 3) == 0);

    f.forced_error = QEMU_DARWIN_PPC_EINTR;
    assert(qemu_darwin_ppc_stdin_read(64, 3, 0, f.base, 1, &ops, &f, &result));
    assert(result.error && result.value == QEMU_DARWIN_PPC_EINTR);
    f.forced_error = 0;
    assert(qemu_darwin_ppc_stdin_read(64, 3, 0, f.base, 0, &ops, &f, &result));
    assert(!result.error && result.value == 0);

    close(pipefd[1]);
    assert(qemu_darwin_ppc_stdin_read(64, 3, 0, f.base, 1, &ops, &f, &result));
    assert(!result.error && result.value == 0);
    close(pipefd[0]);
    return 0;
}
