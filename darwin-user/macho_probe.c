/*
 * Host-independent Darwin Mach-O probe.
 *
 * PowerPC Darwin makes byte order a first-class loader property: classic PPC
 * Mach-O is big-endian, while Intel and AArch64 Mach-O are little-endian.
 * Parse bytes explicitly rather than casting file data onto host C structs.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "darwin-user/include/macho_probe.h"
#include "darwin-user/include/target_macho.h"

#include <string.h>

static uint32_t read_u32(const uint8_t *p, QemuDarwinMachOEndian endian)
{
    if (endian == QEMU_DARWIN_MACHO_BIG_ENDIAN) {
        return ((uint32_t)p[0] << 24) |
               ((uint32_t)p[1] << 16) |
               ((uint32_t)p[2] << 8) |
               (uint32_t)p[3];
    }

    return (uint32_t)p[0] |
           ((uint32_t)p[1] << 8) |
           ((uint32_t)p[2] << 16) |
           ((uint32_t)p[3] << 24);
}

static bool detect_magic(const uint8_t *data, bool *is_64,
                         QemuDarwinMachOEndian *endian)
{
    static const uint8_t be32[] = { 0xfe, 0xed, 0xfa, 0xce };
    static const uint8_t le32[] = { 0xce, 0xfa, 0xed, 0xfe };
    static const uint8_t be64[] = { 0xfe, 0xed, 0xfa, 0xcf };
    static const uint8_t le64[] = { 0xcf, 0xfa, 0xed, 0xfe };

    if (memcmp(data, be32, sizeof(be32)) == 0) {
        *is_64 = false;
        *endian = QEMU_DARWIN_MACHO_BIG_ENDIAN;
        return true;
    }
    if (memcmp(data, le32, sizeof(le32)) == 0) {
        *is_64 = false;
        *endian = QEMU_DARWIN_MACHO_LITTLE_ENDIAN;
        return true;
    }
    if (memcmp(data, be64, sizeof(be64)) == 0) {
        *is_64 = true;
        *endian = QEMU_DARWIN_MACHO_BIG_ENDIAN;
        return true;
    }
    if (memcmp(data, le64, sizeof(le64)) == 0) {
        *is_64 = true;
        *endian = QEMU_DARWIN_MACHO_LITTLE_ENDIAN;
        return true;
    }

    return false;
}

int qemu_darwin_macho_probe(const uint8_t *data, size_t size,
                            QemuDarwinMachOInfo *info)
{
    QemuDarwinMachOInfo parsed = { 0 };
    size_t header_size;

    if (data == NULL || info == NULL || size < sizeof(uint32_t)) {
        return -1;
    }

    if (!detect_magic(data, &parsed.is_64, &parsed.endian)) {
        return -1;
    }

    header_size = parsed.is_64 ? sizeof(QemuDarwinMachHeader64)
                               : sizeof(QemuDarwinMachHeader32);
    if (size < header_size) {
        return -1;
    }

    parsed.cputype = (int32_t)read_u32(data + 4, parsed.endian);
    parsed.cpusubtype = (int32_t)read_u32(data + 8, parsed.endian);
    parsed.filetype = read_u32(data + 12, parsed.endian);
    parsed.ncmds = read_u32(data + 16, parsed.endian);
    parsed.sizeofcmds = read_u32(data + 20, parsed.endian);
    parsed.flags = read_u32(data + 24, parsed.endian);

    if ((size_t)parsed.sizeofcmds > size - header_size) {
        return -1;
    }

    *info = parsed;
    return 0;
}
