#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


def main() -> int:
    cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
    if not cc:
        raise SystemExit("error: C compiler is required for Darwin PPC Mach-O format test")

    source = r'''
#include "darwin-user/include/macho_probe.h"
#include "darwin-user/include/target_macho.h"
#include "darwin-user/ppc/target_abi.h"

#include <stdint.h>
#include <string.h>

static void put_be32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

static void put_be64(uint8_t *p, uint64_t value)
{
    put_be32(p, (uint32_t)(value >> 32));
    put_be32(p + 4, (uint32_t)value);
}

static size_t build_ppc32(uint8_t *image, size_t capacity)
{
    const size_t header_size = sizeof(QemuDarwinMachHeader32);
    const size_t segment_size = sizeof(QemuDarwinSegmentCommand32) +
                                sizeof(QemuDarwinSection32);
    const size_t thread_size = sizeof(QemuDarwinLoadCommand) +
                               sizeof(QemuDarwinThreadStateHeader) +
                               sizeof(QemuDarwinPpcThreadState32);
    const size_t command_size = segment_size + thread_size;
    const size_t fileoff = header_size + command_size;
    const size_t total = fileoff + 16;
    uint8_t *segment;
    uint8_t *section;
    uint8_t *thread;
    uint8_t *state;

    if (capacity < total) {
        return 0;
    }
    memset(image, 0, total);

    put_be32(image + 0, QEMU_DARWIN_MH_MAGIC);
    put_be32(image + 4, QEMU_DARWIN_CPU_TYPE_POWERPC);
    put_be32(image + 8, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400);
    put_be32(image + 12, QEMU_DARWIN_MH_EXECUTE);
    put_be32(image + 16, 2);
    put_be32(image + 20, (uint32_t)command_size);

    segment = image + header_size;
    put_be32(segment + 0, QEMU_DARWIN_LC_SEGMENT);
    put_be32(segment + 4, (uint32_t)segment_size);
    memcpy(segment + 8, "__TEXT", 6);
    put_be32(segment + 24, 0x1000);
    put_be32(segment + 28, 0x1000);
    put_be32(segment + 32, (uint32_t)fileoff);
    put_be32(segment + 36, 16);
    put_be32(segment + 40, 7);
    put_be32(segment + 44, 5);
    put_be32(segment + 48, 1);

    section = segment + sizeof(QemuDarwinSegmentCommand32);
    memcpy(section + 0, "__text", 6);
    memcpy(section + 16, "__TEXT", 6);
    put_be32(section + 32, 0x1000);
    put_be32(section + 36, 16);
    put_be32(section + 40, (uint32_t)fileoff);
    put_be32(section + 44, 2);
    put_be32(section + 56, QEMU_DARWIN_S_REGULAR);

    thread = segment + segment_size;
    put_be32(thread + 0, QEMU_DARWIN_LC_UNIXTHREAD);
    put_be32(thread + 4, (uint32_t)thread_size);
    put_be32(thread + 8, QEMU_DARWIN_PPC_THREAD_STATE);
    put_be32(thread + 12, QEMU_DARWIN_PPC_THREAD_STATE_COUNT);
    state = thread + 16;
    put_be32(state + 0, 0x1000);
    put_be32(state + 12, 0x7fffe000);

    return total;
}

static size_t build_ppc64(uint8_t *image, size_t capacity)
{
    const size_t header_size = sizeof(QemuDarwinMachHeader64);
    const size_t segment_size = sizeof(QemuDarwinSegmentCommand64) +
                                sizeof(QemuDarwinSection64);
    const size_t thread_size = sizeof(QemuDarwinLoadCommand) +
                               sizeof(QemuDarwinThreadStateHeader) +
                               sizeof(QemuDarwinPpcThreadState64);
    const size_t command_size = segment_size + thread_size;
    const size_t fileoff = header_size + command_size;
    const size_t total = fileoff + 16;
    const uint64_t vmaddr = UINT64_C(0x100000000);
    uint8_t *segment;
    uint8_t *section;
    uint8_t *thread;
    uint8_t *state;

    if (capacity < total) {
        return 0;
    }
    memset(image, 0, total);

    put_be32(image + 0, QEMU_DARWIN_MH_MAGIC_64);
    put_be32(image + 4, QEMU_DARWIN_CPU_TYPE_POWERPC64);
    put_be32(image + 8, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_970);
    put_be32(image + 12, QEMU_DARWIN_MH_EXECUTE);
    put_be32(image + 16, 2);
    put_be32(image + 20, (uint32_t)command_size);

    segment = image + header_size;
    put_be32(segment + 0, QEMU_DARWIN_LC_SEGMENT_64);
    put_be32(segment + 4, (uint32_t)segment_size);
    memcpy(segment + 8, "__TEXT", 6);
    put_be64(segment + 24, vmaddr);
    put_be64(segment + 32, 0x1000);
    put_be64(segment + 40, fileoff);
    put_be64(segment + 48, 16);
    put_be32(segment + 56, 7);
    put_be32(segment + 60, 5);
    put_be32(segment + 64, 1);

    section = segment + sizeof(QemuDarwinSegmentCommand64);
    memcpy(section + 0, "__text", 6);
    memcpy(section + 16, "__TEXT", 6);
    put_be64(section + 32, vmaddr);
    put_be64(section + 40, 16);
    put_be32(section + 48, (uint32_t)fileoff);
    put_be32(section + 52, 2);
    put_be32(section + 64, QEMU_DARWIN_S_REGULAR);

    thread = segment + segment_size;
    put_be32(thread + 0, QEMU_DARWIN_LC_UNIXTHREAD);
    put_be32(thread + 4, (uint32_t)thread_size);
    put_be32(thread + 8, QEMU_DARWIN_PPC_THREAD_STATE64);
    put_be32(thread + 12, QEMU_DARWIN_PPC_THREAD_STATE64_COUNT);
    state = thread + 16;
    put_be64(state + 0, vmaddr);
    put_be64(state + 24, UINT64_C(0x7fff00000000));

    return total;
}

int main(void)
{
    uint8_t ppc32[1024];
    uint8_t ppc64[1024];
    uint8_t fat[0x3000];
    uint8_t fat64[0x2000];
    uint8_t damaged[1024];
    size_t ppc32_size = build_ppc32(ppc32, sizeof(ppc32));
    size_t ppc64_size = build_ppc64(ppc64, sizeof(ppc64));
    QemuDarwinMachOInfo info;
    const uint8_t *slice;
    size_t slice_size;
    uint64_t entry;

    if (ppc32_size == 0 || ppc64_size == 0) {
        return 1;
    }

    if (qemu_darwin_macho_probe(ppc32, ppc32_size, &info) != 0 ||
        info.is_64 || info.cputype != QEMU_DARWIN_CPU_TYPE_POWERPC ||
        qemu_darwin_macho_validate(ppc32, ppc32_size, &info) != 0 ||
        qemu_darwin_macho_ppc_entry(ppc32, ppc32_size, &entry) != 0 ||
        entry != UINT64_C(0x1000)) {
        return 2;
    }

    if (qemu_darwin_macho_probe(ppc64, ppc64_size, &info) != 0 ||
        !info.is_64 || info.cputype != QEMU_DARWIN_CPU_TYPE_POWERPC64 ||
        qemu_darwin_macho_validate(ppc64, ppc64_size, &info) != 0 ||
        qemu_darwin_macho_ppc_entry(ppc64, ppc64_size, &entry) != 0 ||
        entry != UINT64_C(0x100000000)) {
        return 3;
    }

    memset(fat, 0, sizeof(fat));
    put_be32(fat + 0, QEMU_DARWIN_FAT_MAGIC);
    put_be32(fat + 4, 2);
    put_be32(fat + 8, QEMU_DARWIN_CPU_TYPE_POWERPC);
    put_be32(fat + 12, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400);
    put_be32(fat + 16, 0x1000);
    put_be32(fat + 20, (uint32_t)ppc32_size);
    put_be32(fat + 24, 12);
    put_be32(fat + 28, QEMU_DARWIN_CPU_TYPE_POWERPC64);
    put_be32(fat + 32, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_970);
    put_be32(fat + 36, 0x2000);
    put_be32(fat + 40, (uint32_t)ppc64_size);
    put_be32(fat + 44, 12);
    memcpy(fat + 0x1000, ppc32, ppc32_size);
    memcpy(fat + 0x2000, ppc64, ppc64_size);

    if (qemu_darwin_macho_select_arch(fat, sizeof(fat),
                                      QEMU_DARWIN_CPU_TYPE_POWERPC,
                                      &slice, &slice_size, &info) != 0 ||
        slice_size != ppc32_size ||
        qemu_darwin_macho_ppc_entry(slice, slice_size, &entry) != 0 ||
        entry != UINT64_C(0x1000)) {
        return 4;
    }
    if (qemu_darwin_macho_select_arch(fat, sizeof(fat),
                                      QEMU_DARWIN_CPU_TYPE_POWERPC64,
                                      &slice, &slice_size, &info) != 0 ||
        slice_size != ppc64_size ||
        qemu_darwin_macho_ppc_entry(slice, slice_size, &entry) != 0 ||
        entry != UINT64_C(0x100000000)) {
        return 5;
    }

    memset(fat64, 0, sizeof(fat64));
    put_be32(fat64 + 0, QEMU_DARWIN_FAT_MAGIC_64);
    put_be32(fat64 + 4, 1);
    put_be32(fat64 + 8, QEMU_DARWIN_CPU_TYPE_POWERPC64);
    put_be32(fat64 + 12, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_970);
    put_be64(fat64 + 16, 0x1000);
    put_be64(fat64 + 24, ppc64_size);
    put_be32(fat64 + 32, 12);
    memcpy(fat64 + 0x1000, ppc64, ppc64_size);
    if (qemu_darwin_macho_select_arch(fat64, sizeof(fat64),
                                      QEMU_DARWIN_CPU_TYPE_POWERPC64,
                                      &slice, &slice_size, &info) != 0 ||
        slice_size != ppc64_size) {
        return 6;
    }

    memcpy(damaged, ppc32, ppc32_size);
    put_be32(damaged + sizeof(QemuDarwinMachHeader32) +
             sizeof(QemuDarwinSegmentCommand32) + 40,
             (uint32_t)(ppc32_size + 32));
    if (qemu_darwin_macho_probe(damaged, ppc32_size, &info) != 0 ||
        qemu_darwin_macho_validate(damaged, ppc32_size, &info) == 0) {
        return 7;
    }

    memcpy(damaged, ppc32, ppc32_size);
    put_be32(damaged + sizeof(QemuDarwinMachHeader32) +
             sizeof(QemuDarwinSegmentCommand32) +
             sizeof(QemuDarwinSection32) + 12,
             QEMU_DARWIN_PPC_THREAD_STATE_COUNT - 1);
    if (qemu_darwin_macho_probe(damaged, ppc32_size, &info) != 0 ||
        qemu_darwin_macho_validate(damaged, ppc32_size, &info) == 0) {
        return 8;
    }

    put_be32(fat + 16, 0x1004);
    if (qemu_darwin_macho_select_arch(fat, sizeof(fat),
                                      QEMU_DARWIN_CPU_TYPE_POWERPC,
                                      &slice, &slice_size, &info) == 0) {
        return 9;
    }

    return 0;
}
'''

    with tempfile.TemporaryDirectory(prefix="whp-darwin-ppc-macho-") as tmp:
        tmpdir = pathlib.Path(tmp)
        src = tmpdir / "format.c"
        exe = tmpdir / "format"
        src.write_text(source, encoding="utf-8")
        subprocess.run(
            [
                cc,
                "-std=c11",
                "-Wall",
                "-Wextra",
                "-Werror",
                "-I",
                str(ROOT),
                str(src),
                str(ROOT / "darwin-user" / "macho_probe.c"),
                "-o",
                str(exe),
            ],
            check=True,
        )
        subprocess.run([str(exe)], check=True)

    print("Darwin PPC32/PPC64 Mach-O format: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
