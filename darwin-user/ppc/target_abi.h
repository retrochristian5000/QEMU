/*
 * Darwin PowerPC target ABI definitions for user-mode emulation.
 *
 * This is guest ABI data. Do not replace these layouts with host SDK
 * definitions: PowerPC Darwin is big-endian and modern build hosts generally
 * are not.
 *
 * Provenance:
 *   Historical QEMU darwin-user/machload.c before
 *   0adb124659cfadf9f0b5c99874c476116f0cf74f.
 *   Darwin/LLVM PowerPC Mach thread-state definitions.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_DARWIN_USER_PPC_TARGET_ABI_H
#define QEMU_DARWIN_USER_PPC_TARGET_ABI_H

#include <stdint.h>

#define QEMU_DARWIN_PPC_THREAD_STATE 1U
#define QEMU_DARWIN_PPC_THREAD_STATE64 5U

typedef struct QemuDarwinPpcThreadState32 {
    uint32_t srr0;
    uint32_t srr1;
    uint32_t r[32];
    uint32_t cr;
    uint32_t xer;
    uint32_t lr;
    uint32_t ctr;
    uint32_t mq;
    uint32_t vrsave;
} QemuDarwinPpcThreadState32;

typedef struct QemuDarwinPpcThreadState64 {
    uint64_t srr0;
    uint64_t srr1;
    uint64_t r[32];
    uint32_t cr;
    uint32_t pad0;
    uint64_t xer;
    uint64_t lr;
    uint64_t ctr;
    uint32_t vrsave;
    uint32_t pad1;
} QemuDarwinPpcThreadState64;

#define QEMU_DARWIN_PPC_THREAD_STATE_COUNT \
    ((uint32_t)(sizeof(QemuDarwinPpcThreadState32) / sizeof(uint32_t)))
#define QEMU_DARWIN_PPC_THREAD_STATE64_COUNT \
    ((uint32_t)(sizeof(QemuDarwinPpcThreadState64) / sizeof(uint32_t)))

_Static_assert(sizeof(QemuDarwinPpcThreadState32) == 160,
               "ppc_thread_state32 ABI");
_Static_assert(sizeof(QemuDarwinPpcThreadState64) == 312,
               "ppc_thread_state64 ABI");
_Static_assert(QEMU_DARWIN_PPC_THREAD_STATE_COUNT == 40,
               "PPC_THREAD_STATE_COUNT ABI");
_Static_assert(QEMU_DARWIN_PPC_THREAD_STATE64_COUNT == 78,
               "PPC_THREAD_STATE64_COUNT ABI");

#endif
