/*
 * Host-independent PowerPC Mach-O executable segment loader plan.
 * Do not use host-native Mach-O structs for big-endian guest images.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#include "darwin-user/include/macho_exec.h"
#include "darwin-user/include/macho_probe.h"
#include "darwin-user/include/target_macho.h"

#include <string.h>

#define DARWIN_MH_DYLDLINK 0x4U
#define DARWIN_LC_LOAD_DYLIB 0xcU
#define DARWIN_LC_LOAD_WEAK_DYLIB 0x80000018U
#define DARWIN_LC_REEXPORT_DYLIB 0x8000001fU
#define DARWIN_LC_LOAD_UPWARD_DYLIB 0x80000023U

static uint32_t be32(const uint8_t *p)
{
    return ((uint32_t)p[0] << 24) | ((uint32_t)p[1] << 16) |
           ((uint32_t)p[2] << 8) | (uint32_t)p[3];
}

static uint64_t be64(const uint8_t *p)
{
    return ((uint64_t)be32(p) << 32) | be32(p + 4);
}

static bool has_overlap(const QemuDarwinPpcExecSegment *a,
                        const QemuDarwinPpcExecSegment *b)
{
    if (!a->vmsize || !b->vmsize) {
        return false;
    }
    return a->vmaddr < b->vmaddr + b->vmsize &&
           b->vmaddr < a->vmaddr + a->vmsize;
}

int qemu_darwin_ppc_executable_plan(const uint8_t *container, size_t size,
                                    int32_t cputype,
                                    QemuDarwinPpcExecSegment *segments,
                                    size_t capacity,
                                    QemuDarwinPpcExecImage *image,
                                    const uint8_t **slice,
                                    size_t *slice_size)
{
    QemuDarwinPpcExecSegment pending[QEMU_DARWIN_PPC_EXEC_MAX_SEGMENTS];
    QemuDarwinMachOInfo info;
    const uint8_t *selected;
    size_t selected_size;
    size_t offset;
    size_t i, nsegments = 0;
    uint64_t entry;
    bool has_executable_entry = false;
    uint64_t address_max;

    if (!container || !segments || !image || !slice || !slice_size ||
        (cputype != QEMU_DARWIN_CPU_TYPE_POWERPC &&
         cputype != QEMU_DARWIN_CPU_TYPE_POWERPC64) ||
        capacity > QEMU_DARWIN_PPC_EXEC_MAX_SEGMENTS ||
        qemu_darwin_macho_select_arch(container, size, cputype,
                                      &selected, &selected_size, &info) != 0 ||
        qemu_darwin_macho_validate(selected, selected_size, &info) != 0 ||
        info.filetype != QEMU_DARWIN_MH_EXECUTE ||
        info.endian != QEMU_DARWIN_MACHO_BIG_ENDIAN ||
        info.is_64 != (cputype == QEMU_DARWIN_CPU_TYPE_POWERPC64)) {
        return QEMU_DARWIN_EXEC_BAD_IMAGE;
    }
    if (info.flags & DARWIN_MH_DYLDLINK) {
        return QEMU_DARWIN_EXEC_NEEDS_DYLD;
    }

    /* Require a direct thread-state entry, not LC_MAIN/dyld semantics. */
    offset = info.is_64 ? sizeof(QemuDarwinMachHeader64)
                        : sizeof(QemuDarwinMachHeader32);
    for (i = 0; i < info.ncmds; i++) {
        const uint8_t *command = selected + offset;
        uint32_t cmd = be32(command);
        uint32_t cmdsize = be32(command + 4);
        QemuDarwinPpcExecSegment seg = { 0 };
        size_t j;

        if (cmd == QEMU_DARWIN_LC_LOAD_DYLINKER ||
            cmd == QEMU_DARWIN_LC_MAIN ||
            cmd == DARWIN_LC_LOAD_DYLIB ||
            cmd == DARWIN_LC_LOAD_WEAK_DYLIB ||
            cmd == DARWIN_LC_REEXPORT_DYLIB ||
            cmd == DARWIN_LC_LOAD_UPWARD_DYLIB ||
            (cmd & QEMU_DARWIN_LC_REQ_DYLD)) {
            return QEMU_DARWIN_EXEC_NEEDS_DYLD;
        }
        if (cmd != QEMU_DARWIN_LC_SEGMENT &&
            cmd != QEMU_DARWIN_LC_SEGMENT_64) {
            offset += cmdsize;
            continue;
        }
        if (nsegments >= capacity) {
            return QEMU_DARWIN_EXEC_BAD_IMAGE;
        }
        seg.vmaddr = info.is_64 ? be64(command + 24) : be32(command + 24);
        seg.vmsize = info.is_64 ? be64(command + 32) : be32(command + 28);
        seg.fileoff = info.is_64 ? be64(command + 40) : be32(command + 32);
        seg.filesize = info.is_64 ? be64(command + 48) : be32(command + 36);
        seg.maxprot = be32(command + (info.is_64 ? 56 : 40));
        seg.initprot = be32(command + (info.is_64 ? 60 : 44));
        address_max = info.is_64 ? UINT64_MAX : UINT32_MAX;

        /* For safety the exclusive end must fit in the guest address type. */
        if (seg.filesize > seg.vmsize ||
            seg.fileoff > selected_size ||
            seg.filesize > selected_size - seg.fileoff ||
            seg.vmsize > address_max - seg.vmaddr ||
            ((seg.initprot | seg.maxprot) & ~7U) ||
            (seg.initprot & ~seg.maxprot)) {
            return QEMU_DARWIN_EXEC_BAD_IMAGE;
        }
        for (j = 0; j < nsegments; j++) {
            if (has_overlap(&pending[j], &seg)) {
                return QEMU_DARWIN_EXEC_BAD_IMAGE;
            }
        }
        pending[nsegments++] = seg;
        offset += cmdsize;
    }

    if (!nsegments ||
        qemu_darwin_macho_ppc_entry(selected, selected_size, &entry) != 0 ||
        (entry & 3U)) {
        return QEMU_DARWIN_EXEC_BAD_IMAGE;
    }
    for (i = 0; i < nsegments; i++) {
        const QemuDarwinPpcExecSegment *seg = &pending[i];

        if ((seg->initprot & QEMU_DARWIN_VM_PROT_EXECUTE) &&
            entry >= seg->vmaddr &&
            entry - seg->vmaddr < seg->filesize) {
            has_executable_entry = true;
        }
    }
    if (!has_executable_entry) {
        return QEMU_DARWIN_EXEC_BAD_IMAGE;
    }

    memcpy(segments, pending, nsegments * sizeof(*segments));
    image->entry = entry;
    image->cputype = cputype;
    image->nsegments = nsegments;
    *slice = selected;
    *slice_size = selected_size;
    return 0;
}

int qemu_darwin_ppc_executable_apply(const uint8_t *slice, size_t size,
                                     const QemuDarwinPpcExecSegment *segments,
                                     size_t count, QemuDarwinPpcMapSegment map,
                                     void *opaque)
{
    size_t i;

    if (!slice || !segments || !map || count > QEMU_DARWIN_PPC_EXEC_MAX_SEGMENTS) {
        return QEMU_DARWIN_EXEC_BAD_IMAGE;
    }
    /* Recheck callback-facing file ranges; never trust a modified plan. */
    for (i = 0; i < count; i++) {
        if (segments[i].fileoff > size ||
            segments[i].filesize > size - segments[i].fileoff ||
            segments[i].filesize > segments[i].vmsize) {
            return QEMU_DARWIN_EXEC_BAD_IMAGE;
        }
    }
    for (i = 0; i < count; i++) {
        if (segments[i].vmsize &&
            !map(opaque, &segments[i], slice + (size_t)segments[i].fileoff)) {
            return QEMU_DARWIN_EXEC_BAD_IMAGE;
        }
    }
    return 0;
}
