/*
 * PowerPC Darwin Mach-O executable image plan (host-independent).
 * The caller provides the guest address-space mapper; this does not start a
 * Darwin task or implement dyld, Mach traps, or guest memory allocation.
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_DARWIN_USER_MACHO_EXEC_H
#define QEMU_DARWIN_USER_MACHO_EXEC_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define QEMU_DARWIN_PPC_EXEC_MAX_SEGMENTS 64U
#define QEMU_DARWIN_VM_PROT_READ 1U
#define QEMU_DARWIN_VM_PROT_WRITE 2U
#define QEMU_DARWIN_VM_PROT_EXECUTE 4U

/* Explicitly distinguish unsupported dyld handoff from corrupt input. */
#define QEMU_DARWIN_EXEC_BAD_IMAGE (-1)
#define QEMU_DARWIN_EXEC_NEEDS_DYLD (-2)

typedef struct QemuDarwinPpcExecSegment {
    uint64_t vmaddr;
    uint64_t vmsize;
    uint64_t fileoff;
    uint64_t filesize;
    uint32_t maxprot;
    uint32_t initprot;
} QemuDarwinPpcExecSegment;

typedef struct QemuDarwinPpcExecImage {
    uint64_t entry;
    int32_t cputype;
    size_t nsegments;
} QemuDarwinPpcExecImage;

typedef bool (*QemuDarwinPpcMapSegment)(void *opaque,
                                         const QemuDarwinPpcExecSegment *seg,
                                         const uint8_t *filebytes);

/* Validate/select a PPC32 or PPC64 MH_EXECUTE and prepare *all* segments
 * before returning them. Returns 0 or a QEMU_DARWIN_EXEC_* error.
 * On error the output objects and caller's segment array are unchanged.
 * The returned slice points into container, which must outlive apply().
 */
int qemu_darwin_ppc_executable_plan(const uint8_t *container, size_t size,
                                    int32_t cputype,
                                    QemuDarwinPpcExecSegment *segments,
                                    size_t capacity,
                                    QemuDarwinPpcExecImage *image,
                                    const uint8_t **slice,
                                    size_t *slice_size);

/* Apply a validated plan to a guest VM backend. The callback MUST reserve
 * each region, copy the file-backed bytes, zero-fill the remaining VM bytes,
 * and enforce initprot/maxprot, including inaccessible __PAGEZERO. On a
 * callback failure the caller MUST tear down any partial guest mappings.
 */
int qemu_darwin_ppc_executable_apply(const uint8_t *slice, size_t size,
                                     const QemuDarwinPpcExecSegment *segments,
                                     size_t count, QemuDarwinPpcMapSegment map,
                                     void *opaque);

#endif
