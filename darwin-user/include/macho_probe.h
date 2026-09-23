/*
 * Host-independent Darwin Mach-O probe.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_DARWIN_USER_MACHO_PROBE_H
#define QEMU_DARWIN_USER_MACHO_PROBE_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

typedef enum QemuDarwinMachOEndian {
    QEMU_DARWIN_MACHO_LITTLE_ENDIAN = 0,
    QEMU_DARWIN_MACHO_BIG_ENDIAN = 1,
} QemuDarwinMachOEndian;

typedef struct QemuDarwinMachOInfo {
    bool is_64;
    QemuDarwinMachOEndian endian;
    int32_t cputype;
    int32_t cpusubtype;
    uint32_t filetype;
    uint32_t ncmds;
    uint32_t sizeofcmds;
    uint32_t flags;
} QemuDarwinMachOInfo;

/*
 * Probe a thin Mach-O header. Return 0 for a structurally valid header and
 * -1 for unsupported magic, truncation, or a load-command region that extends
 * beyond the supplied buffer.
 */
int qemu_darwin_macho_probe(const uint8_t *data, size_t size,
                            QemuDarwinMachOInfo *info);

#endif
