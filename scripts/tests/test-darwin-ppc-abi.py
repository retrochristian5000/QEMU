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
        raise SystemExit("error: C compiler is required for Darwin PPC ABI test")

    source = r'''
#include "darwin-user/include/macho_probe.h"
#include "darwin-user/include/target_macho.h"
#include "darwin-user/ppc/target_abi.h"

#include <stdint.h>

static void put_be32(uint8_t *p, uint32_t value)
{
    p[0] = (uint8_t)(value >> 24);
    p[1] = (uint8_t)(value >> 16);
    p[2] = (uint8_t)(value >> 8);
    p[3] = (uint8_t)value;
}

int main(void)
{
    uint8_t image[sizeof(QemuDarwinMachHeader32) + 8] = { 0 };
    QemuDarwinMachOInfo info;

    /* Classic PowerPC Darwin Mach-O is big-endian. */
    image[0] = 0xfe;
    image[1] = 0xed;
    image[2] = 0xfa;
    image[3] = 0xce;
    put_be32(image + 4, QEMU_DARWIN_CPU_TYPE_POWERPC);
    put_be32(image + 8, QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400);
    put_be32(image + 12, QEMU_DARWIN_MH_EXECUTE);
    put_be32(image + 16, 1);
    put_be32(image + 20, 8);
    put_be32(image + 24, 0);

    if (qemu_darwin_macho_probe(image, sizeof(image), &info) != 0) {
        return 1;
    }
    if (info.is_64 ||
        info.endian != QEMU_DARWIN_MACHO_BIG_ENDIAN ||
        info.cputype != QEMU_DARWIN_CPU_TYPE_POWERPC ||
        info.cpusubtype != QEMU_DARWIN_CPU_SUBTYPE_POWERPC_7400 ||
        info.filetype != QEMU_DARWIN_MH_EXECUTE ||
        info.ncmds != 1 ||
        info.sizeofcmds != 8) {
        return 2;
    }

    if (QEMU_DARWIN_PPC_THREAD_STATE != 1 ||
        QEMU_DARWIN_PPC_THREAD_STATE_COUNT != 40 ||
        sizeof(QemuDarwinPpcThreadState32) != 160) {
        return 3;
    }

    /* A command region extending beyond the input must be rejected. */
    put_be32(image + 20, 12);
    if (qemu_darwin_macho_probe(image, sizeof(image), &info) == 0) {
        return 4;
    }

    return 0;
}
'''

    with tempfile.TemporaryDirectory(prefix="whp-darwin-ppc-") as tmp:
        tmpdir = pathlib.Path(tmp)
        src = tmpdir / "probe.c"
        exe = tmpdir / "probe"
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

    print("Darwin PowerPC ABI and big-endian Mach-O probe: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
