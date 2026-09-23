/*
 * Darwin/Mach-O target ABI definitions for user-mode emulation.
 *
 * Keep this header independent of the host macOS SDK.  These structures
 * describe the guest file ABI and must compile identically on Darwin, Linux,
 * and other supported QEMU build hosts.
 *
 * Provenance:
 *   Apple XNU external Mach-O headers (mach-o/loader.h, mach/machine.h).
 *   Historical QEMU darwin-user tree before 0adb124659cfadf9f0b5c99874c476116f0cf74f.
 *
 * SPDX-License-Identifier: GPL-2.0-or-later
 */
#ifndef QEMU_DARWIN_USER_TARGET_MACHO_H
#define QEMU_DARWIN_USER_TARGET_MACHO_H

#include <stdint.h>

typedef int32_t QemuDarwinCpuType;
typedef int32_t QemuDarwinCpuSubtype;
typedef int32_t QemuDarwinVmProt;

/* mach/machine.h */
#define QEMU_DARWIN_CPU_ARCH_ABI64 0x01000000
#define QEMU_DARWIN_CPU_TYPE_X86      7
#define QEMU_DARWIN_CPU_TYPE_ARM      12
#define QEMU_DARWIN_CPU_TYPE_POWERPC  18
#define QEMU_DARWIN_CPU_TYPE_X86_64 \
    (QEMU_DARWIN_CPU_TYPE_X86 | QEMU_DARWIN_CPU_ARCH_ABI64)
#define QEMU_DARWIN_CPU_TYPE_POWERPC64 \
    (QEMU_DARWIN_CPU_TYPE_POWERPC | QEMU_DARWIN_CPU_ARCH_ABI64)
#define QEMU_DARWIN_CPU_TYPE_ARM64 \
    (QEMU_DARWIN_CPU_TYPE_ARM | QEMU_DARWIN_CPU_ARCH_ABI64)

#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_ALL   0
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_601   1
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_603   3
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_604   6
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_750   9
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400 10
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7450 11
#define QEMU_DARWIN_CPU_SUBTYPE_POWERPC_970 100

/* mach-o/loader.h */
#define QEMU_DARWIN_MH_MAGIC    0xfeedfaceU
#define QEMU_DARWIN_MH_CIGAM    0xcefaedfeU
#define QEMU_DARWIN_MH_MAGIC_64 0xfeedfacfU
#define QEMU_DARWIN_MH_CIGAM_64 0xcffaedfeU
#define QEMU_DARWIN_FAT_MAGIC    0xcafebabeU
#define QEMU_DARWIN_FAT_CIGAM    0xbebafecaU
#define QEMU_DARWIN_FAT_MAGIC_64 0xcafebabfU
#define QEMU_DARWIN_FAT_CIGAM_64 0xbfbafecaU

#define QEMU_DARWIN_MH_EXECUTE 0x2U
#define QEMU_DARWIN_MH_DYLINKER 0x7U

#define QEMU_DARWIN_LC_REQ_DYLD 0x80000000U
#define QEMU_DARWIN_LC_SEGMENT 0x01U
#define QEMU_DARWIN_LC_THREAD 0x04U
#define QEMU_DARWIN_LC_UNIXTHREAD 0x05U
#define QEMU_DARWIN_LC_LOAD_DYLINKER 0x0eU
#define QEMU_DARWIN_LC_SEGMENT_64 0x19U
#define QEMU_DARWIN_LC_DYLD_INFO_ONLY \
    (0x22U | QEMU_DARWIN_LC_REQ_DYLD)
#define QEMU_DARWIN_LC_MAIN \
    (0x28U | QEMU_DARWIN_LC_REQ_DYLD)
#define QEMU_DARWIN_LC_BUILD_VERSION 0x32U
#define QEMU_DARWIN_LC_DYLD_EXPORTS_TRIE \
    (0x33U | QEMU_DARWIN_LC_REQ_DYLD)
#define QEMU_DARWIN_LC_DYLD_CHAINED_FIXUPS \
    (0x34U | QEMU_DARWIN_LC_REQ_DYLD)

typedef struct QemuDarwinFatHeader {
    uint32_t magic;
    uint32_t nfat_arch;
} QemuDarwinFatHeader;

typedef struct QemuDarwinFatArch32 {
    QemuDarwinCpuType cputype;
    QemuDarwinCpuSubtype cpusubtype;
    uint32_t offset;
    uint32_t size;
    uint32_t align;
} QemuDarwinFatArch32;

typedef struct QemuDarwinFatArch64 {
    QemuDarwinCpuType cputype;
    QemuDarwinCpuSubtype cpusubtype;
    uint64_t offset;
    uint64_t size;
    uint32_t align;
    uint32_t reserved;
} QemuDarwinFatArch64;
typedef struct QemuDarwinMachHeader32 {
    uint32_t magic;
    QemuDarwinCpuType cputype;
    QemuDarwinCpuSubtype cpusubtype;
    uint32_t filetype;
    uint32_t ncmds;
    uint32_t sizeofcmds;
    uint32_t flags;
} QemuDarwinMachHeader32;

typedef struct QemuDarwinMachHeader64 {
    uint32_t magic;
    QemuDarwinCpuType cputype;
    QemuDarwinCpuSubtype cpusubtype;
    uint32_t filetype;
    uint32_t ncmds;
    uint32_t sizeofcmds;
    uint32_t flags;
    uint32_t reserved;
} QemuDarwinMachHeader64;

typedef struct QemuDarwinLoadCommand {
    uint32_t cmd;
    uint32_t cmdsize;
} QemuDarwinLoadCommand;

typedef struct QemuDarwinSegmentCommand32 {
    uint32_t cmd;
    uint32_t cmdsize;
    char segname[16];
    uint32_t vmaddr;
    uint32_t vmsize;
    uint32_t fileoff;
    uint32_t filesize;
    QemuDarwinVmProt maxprot;
    QemuDarwinVmProt initprot;
    uint32_t nsects;
    uint32_t flags;
} QemuDarwinSegmentCommand32;

typedef struct QemuDarwinSection32 {
    char sectname[16];
    char segname[16];
    uint32_t addr;
    uint32_t size;
    uint32_t offset;
    uint32_t align;
    uint32_t reloff;
    uint32_t nreloc;
    uint32_t flags;
    uint32_t reserved1;
    uint32_t reserved2;
} QemuDarwinSection32;
typedef struct QemuDarwinSegmentCommand64 {
    uint32_t cmd;
    uint32_t cmdsize;
    char segname[16];
    uint64_t vmaddr;
    uint64_t vmsize;
    uint64_t fileoff;
    uint64_t filesize;
    QemuDarwinVmProt maxprot;
    QemuDarwinVmProt initprot;
    uint32_t nsects;
    uint32_t flags;
} QemuDarwinSegmentCommand64;

typedef struct QemuDarwinSection64 {
    char sectname[16];
    char segname[16];
    uint64_t addr;
    uint64_t size;
    uint32_t offset;
    uint32_t align;
    uint32_t reloff;
    uint32_t nreloc;
    uint32_t flags;
    uint32_t reserved1;
    uint32_t reserved2;
    uint32_t reserved3;
} QemuDarwinSection64;

typedef struct QemuDarwinThreadStateHeader {
    uint32_t flavor;
    uint32_t count;
} QemuDarwinThreadStateHeader;
typedef struct QemuDarwinEntryPointCommand {
    uint32_t cmd;
    uint32_t cmdsize;
    uint64_t entryoff;
    uint64_t stacksize;
} QemuDarwinEntryPointCommand;

typedef struct QemuDarwinLcStr {
    uint32_t offset;
} QemuDarwinLcStr;

typedef struct QemuDarwinDylinkerCommand {
    uint32_t cmd;
    uint32_t cmdsize;
    QemuDarwinLcStr name;
} QemuDarwinDylinkerCommand;

typedef struct QemuDarwinLinkeditDataCommand {
    uint32_t cmd;
    uint32_t cmdsize;
    uint32_t dataoff;
    uint32_t datasize;
} QemuDarwinLinkeditDataCommand;

typedef struct QemuDarwinBuildVersionCommand {
    uint32_t cmd;
    uint32_t cmdsize;
    uint32_t platform;
    uint32_t minos;
    uint32_t sdk;
    uint32_t ntools;
} QemuDarwinBuildVersionCommand;

/*
 * These are on-disk ABI sizes.  If a compiler changes any of them, fail at
 * compile time instead of letting a loader silently parse host-shaped data.
 */
_Static_assert(sizeof(QemuDarwinCpuType) == 4, "Darwin cpu_type_t ABI");
_Static_assert(sizeof(QemuDarwinCpuSubtype) == 4, "Darwin cpu_subtype_t ABI");
_Static_assert(sizeof(QemuDarwinVmProt) == 4, "Darwin vm_prot_t ABI");
_Static_assert(sizeof(QemuDarwinFatHeader) == 8, "fat_header ABI");
_Static_assert(sizeof(QemuDarwinFatArch32) == 20, "fat_arch ABI");
_Static_assert(sizeof(QemuDarwinFatArch64) == 32, "fat_arch_64 ABI");
_Static_assert(sizeof(QemuDarwinMachHeader32) == 28, "mach_header ABI");
_Static_assert(sizeof(QemuDarwinMachHeader64) == 32, "mach_header_64 ABI");
_Static_assert(sizeof(QemuDarwinLoadCommand) == 8, "load_command ABI");
_Static_assert(sizeof(QemuDarwinSegmentCommand32) == 56,
               "segment_command ABI");
_Static_assert(sizeof(QemuDarwinSection32) == 68, "section ABI");
_Static_assert(sizeof(QemuDarwinSegmentCommand64) == 72,
               "segment_command_64 ABI");
_Static_assert(sizeof(QemuDarwinSection64) == 80, "section_64 ABI");
_Static_assert(sizeof(QemuDarwinThreadStateHeader) == 8,
               "thread state header ABI");
_Static_assert(sizeof(QemuDarwinEntryPointCommand) == 24,
               "entry_point_command ABI");
_Static_assert(sizeof(QemuDarwinLcStr) == 4, "lc_str ABI");
_Static_assert(sizeof(QemuDarwinDylinkerCommand) == 12,
               "dylinker_command ABI");
_Static_assert(sizeof(QemuDarwinLinkeditDataCommand) == 16,
               "linkedit_data_command ABI");
_Static_assert(sizeof(QemuDarwinBuildVersionCommand) == 24,
               "build_version_command ABI");

#endif
