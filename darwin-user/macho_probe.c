/*
 * Host-independent Darwin Mach-O probe.
 *
 * PowerPC Darwin makes byte order a first-class loader property: PPC32 and
 * PPC64 Mach-O are big-endian, while Intel and AArch64 Mach-O are normally
 * little-endian. Parse bytes explicitly rather than casting file data onto
 * host C structs.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */

#include "darwin-user/include/macho_probe.h"
#include "darwin-user/include/target_macho.h"
#include "darwin-user/ppc/target_abi.h"

#include <limits.h>
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

static uint64_t read_u64(const uint8_t *p, QemuDarwinMachOEndian endian)
{
    uint64_t hi;
    uint64_t lo;

    if (endian == QEMU_DARWIN_MACHO_BIG_ENDIAN) {
        hi = read_u32(p, endian);
        lo = read_u32(p + 4, endian);
    } else {
        lo = read_u32(p, endian);
        hi = read_u32(p + 4, endian);
    }
    return (hi << 32) | lo;
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

static bool detect_fat_magic(const uint8_t *data, bool *is_64,
                             QemuDarwinMachOEndian *endian)
{
    static const uint8_t be32[] = { 0xca, 0xfe, 0xba, 0xbe };
    static const uint8_t le32[] = { 0xbe, 0xba, 0xfe, 0xca };
    static const uint8_t be64[] = { 0xca, 0xfe, 0xba, 0xbf };
    static const uint8_t le64[] = { 0xbf, 0xba, 0xfe, 0xca };

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

static size_t macho_header_size(const QemuDarwinMachOInfo *info)
{
    return info->is_64 ? sizeof(QemuDarwinMachHeader64)
                       : sizeof(QemuDarwinMachHeader32);
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

    header_size = macho_header_size(&parsed);
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

int qemu_darwin_macho_select_arch(const uint8_t *data, size_t size,
                                  int32_t cputype,
                                  const uint8_t **slice, size_t *slice_size,
                                  QemuDarwinMachOInfo *info)
{
    bool fat64;
    QemuDarwinMachOEndian endian;
    QemuDarwinMachOInfo thin;
    uint32_t narch;
    size_t arch_size;
    size_t table_size;
    size_t i;

    if (data == NULL || slice == NULL || slice_size == NULL || info == NULL) {
        return -1;
    }

    if (qemu_darwin_macho_probe(data, size, &thin) == 0) {
        if (thin.cputype != cputype) {
            return -1;
        }
        *slice = data;
        *slice_size = size;
        *info = thin;
        return 0;
    }

    if (size < sizeof(QemuDarwinFatHeader) ||
        !detect_fat_magic(data, &fat64, &endian)) {
        return -1;
    }

    narch = read_u32(data + 4, endian);
    arch_size = fat64 ? sizeof(QemuDarwinFatArch64)
                      : sizeof(QemuDarwinFatArch32);
    if (narch > (SIZE_MAX - sizeof(QemuDarwinFatHeader)) / arch_size) {
        return -1;
    }
    table_size = sizeof(QemuDarwinFatHeader) + (size_t)narch * arch_size;
    if (table_size > size) {
        return -1;
    }

    for (i = 0; i < narch; i++) {
        const uint8_t *arch = data + sizeof(QemuDarwinFatHeader) + i * arch_size;
        int32_t arch_cpu = (int32_t)read_u32(arch, endian);
        uint64_t offset;
        uint64_t arch_bytes;
        QemuDarwinMachOInfo selected;

        if (fat64) {
            offset = read_u64(arch + 8, endian);
            arch_bytes = read_u64(arch + 16, endian);
        } else {
            offset = read_u32(arch + 8, endian);
            arch_bytes = read_u32(arch + 12, endian);
        }

        if (offset > size || arch_bytes > (uint64_t)size - offset) {
            return -1;
        }
        if (arch_cpu != cputype) {
            continue;
        }
        if (arch_bytes > SIZE_MAX ||
            qemu_darwin_macho_probe(data + (size_t)offset,
                                    (size_t)arch_bytes, &selected) != 0 ||
            selected.cputype != cputype) {
            return -1;
        }

        *slice = data + (size_t)offset;
        *slice_size = (size_t)arch_bytes;
        *info = selected;
        return 0;
    }

    return -1;
}

static int validate_thread_command(const uint8_t *command, uint32_t cmdsize,
                                   QemuDarwinMachOEndian endian)
{
    size_t offset = sizeof(QemuDarwinLoadCommand);

    while (offset < cmdsize) {
        uint32_t count;
        size_t state_bytes;

        if (cmdsize - offset < sizeof(QemuDarwinThreadStateHeader)) {
            return -1;
        }
        count = read_u32(command + offset + 4, endian);
        if (count > SIZE_MAX / sizeof(uint32_t)) {
            return -1;
        }
        state_bytes = (size_t)count * sizeof(uint32_t);
        offset += sizeof(QemuDarwinThreadStateHeader);
        if (state_bytes > cmdsize - offset) {
            return -1;
        }
        offset += state_bytes;
    }

    return offset == cmdsize ? 0 : -1;
}

static int validate_segment32(const uint8_t *data, size_t size,
                              const uint8_t *command, uint32_t cmdsize,
                              QemuDarwinMachOEndian endian)
{
    uint32_t nsects;
    uint32_t fileoff;
    uint32_t filesize;
    size_t required;

    if (cmdsize < sizeof(QemuDarwinSegmentCommand32)) {
        return -1;
    }
    nsects = read_u32(command + 48, endian);
    if (nsects > (SIZE_MAX - sizeof(QemuDarwinSegmentCommand32)) /
                 sizeof(QemuDarwinSection32)) {
        return -1;
    }
    required = sizeof(QemuDarwinSegmentCommand32) +
               (size_t)nsects * sizeof(QemuDarwinSection32);
    if (required != cmdsize) {
        return -1;
    }

    fileoff = read_u32(command + 32, endian);
    filesize = read_u32(command + 36, endian);
    if ((size_t)fileoff > size || (size_t)filesize > size - fileoff) {
        return -1;
    }
    (void)data;
    return 0;
}

static int validate_segment64(const uint8_t *data, size_t size,
                              const uint8_t *command, uint32_t cmdsize,
                              QemuDarwinMachOEndian endian)
{
    uint32_t nsects;
    uint64_t fileoff;
    uint64_t filesize;
    size_t required;

    if (cmdsize < sizeof(QemuDarwinSegmentCommand64)) {
        return -1;
    }
    nsects = read_u32(command + 64, endian);
    if (nsects > (SIZE_MAX - sizeof(QemuDarwinSegmentCommand64)) /
                 sizeof(QemuDarwinSection64)) {
        return -1;
    }
    required = sizeof(QemuDarwinSegmentCommand64) +
               (size_t)nsects * sizeof(QemuDarwinSection64);
    if (required != cmdsize) {
        return -1;
    }

    fileoff = read_u64(command + 40, endian);
    filesize = read_u64(command + 48, endian);
    if (fileoff > size || filesize > (uint64_t)size - fileoff) {
        return -1;
    }
    (void)data;
    return 0;
}

int qemu_darwin_macho_validate(const uint8_t *data, size_t size,
                               const QemuDarwinMachOInfo *info)
{
    size_t offset;
    size_t command_end;
    uint32_t i;

    if (data == NULL || info == NULL) {
        return -1;
    }
    offset = macho_header_size(info);
    if ((size_t)info->sizeofcmds > size - offset) {
        return -1;
    }
    command_end = offset + info->sizeofcmds;

    for (i = 0; i < info->ncmds; i++) {
        const uint8_t *command;
        uint32_t cmd;
        uint32_t cmdsize;
        uint32_t alignment = info->is_64 ? 8U : 4U;

        if (command_end - offset < sizeof(QemuDarwinLoadCommand)) {
            return -1;
        }
        command = data + offset;
        cmd = read_u32(command, info->endian);
        cmdsize = read_u32(command + 4, info->endian);
        if (cmdsize < sizeof(QemuDarwinLoadCommand) ||
            cmdsize > command_end - offset ||
            (cmdsize % alignment) != 0) {
            return -1;
        }

        if (cmd == QEMU_DARWIN_LC_SEGMENT) {
            if (info->is_64 ||
                validate_segment32(data, size, command, cmdsize,
                                   info->endian) != 0) {
                return -1;
            }
        } else if (cmd == QEMU_DARWIN_LC_SEGMENT_64) {
            if (!info->is_64 ||
                validate_segment64(data, size, command, cmdsize,
                                   info->endian) != 0) {
                return -1;
            }
        } else if (cmd == QEMU_DARWIN_LC_THREAD ||
                   cmd == QEMU_DARWIN_LC_UNIXTHREAD) {
            if (validate_thread_command(command, cmdsize, info->endian) != 0) {
                return -1;
            }
        }

        offset += cmdsize;
    }

    return offset == command_end ? 0 : -1;
}

int qemu_darwin_macho_ppc_entry(const uint8_t *data, size_t size,
                                uint64_t *entry)
{
    QemuDarwinMachOInfo info;
    size_t offset;
    size_t command_end;
    uint32_t i;

    if (entry == NULL || qemu_darwin_macho_probe(data, size, &info) != 0 ||
        qemu_darwin_macho_validate(data, size, &info) != 0 ||
        info.endian != QEMU_DARWIN_MACHO_BIG_ENDIAN ||
        (info.cputype != QEMU_DARWIN_CPU_TYPE_POWERPC &&
         info.cputype != QEMU_DARWIN_CPU_TYPE_POWERPC64)) {
        return -1;
    }
    if ((info.cputype == QEMU_DARWIN_CPU_TYPE_POWERPC64) != info.is_64) {
        return -1;
    }

    offset = macho_header_size(&info);
    command_end = offset + info.sizeofcmds;
    for (i = 0; i < info.ncmds; i++) {
        const uint8_t *command = data + offset;
        uint32_t cmd = read_u32(command, info.endian);
        uint32_t cmdsize = read_u32(command + 4, info.endian);

        if (cmd == QEMU_DARWIN_LC_UNIXTHREAD ||
            cmd == QEMU_DARWIN_LC_THREAD) {
            size_t state_off = sizeof(QemuDarwinLoadCommand);

            while (state_off < cmdsize) {
                uint32_t flavor = read_u32(command + state_off, info.endian);
                uint32_t count = read_u32(command + state_off + 4, info.endian);
                size_t state_bytes = (size_t)count * sizeof(uint32_t);
                const uint8_t *state = command + state_off +
                                       sizeof(QemuDarwinThreadStateHeader);

                if (!info.is_64 &&
                    flavor == QEMU_DARWIN_PPC_THREAD_STATE &&
                    count == QEMU_DARWIN_PPC_THREAD_STATE_COUNT) {
                    *entry = read_u32(state, info.endian);
                    return 0;
                }
                if (info.is_64 &&
                    flavor == QEMU_DARWIN_PPC_THREAD_STATE64 &&
                    count == QEMU_DARWIN_PPC_THREAD_STATE64_COUNT) {
                    *entry = read_u64(state, info.endian);
                    return 0;
                }

                state_off += sizeof(QemuDarwinThreadStateHeader) + state_bytes;
            }
        }
        offset += cmdsize;
    }

    (void)command_end;
    return -1;
}
