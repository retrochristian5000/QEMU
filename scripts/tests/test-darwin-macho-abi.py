#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HEADER = ROOT / "darwin-user" / "include" / "target_macho.h"


def main() -> int:
    text = HEADER.read_text(encoding="utf-8")
    required = (
        "QEMU_DARWIN_MH_MAGIC_64",
        "QEMU_DARWIN_CPU_TYPE_X86_64",
        "QEMU_DARWIN_CPU_TYPE_ARM64",
        "QEMU_DARWIN_LC_SEGMENT_64",
        "QEMU_DARWIN_LC_MAIN",
        "QEMU_DARWIN_LC_DYLD_INFO_ONLY",
        "QEMU_DARWIN_LC_BUILD_VERSION",
        "QEMU_DARWIN_LC_DYLD_EXPORTS_TRIE",
        "QEMU_DARWIN_LC_DYLD_CHAINED_FIXUPS",
        "QemuDarwinMachHeader64",
        "QemuDarwinSegmentCommand64",
        "QemuDarwinEntryPointCommand",
        "_Static_assert(sizeof(QemuDarwinMachHeader64) == 32",
        "_Static_assert(sizeof(QemuDarwinSegmentCommand64) == 72",
    )
    for needle in required:
        if needle not in text:
            raise SystemExit(f"error: Darwin Mach-O ABI header lost {needle}")

    cc = os.environ.get("CC") or shutil.which("cc") or shutil.which("clang")
    if not cc:
        raise SystemExit("error: C compiler is required for Darwin Mach-O ABI test")

    source = r"""
#include "darwin-user/include/target_macho.h"

int main(void)
{
    QemuDarwinMachHeader64 header = {
        .magic = QEMU_DARWIN_MH_MAGIC_64,
        .cputype = QEMU_DARWIN_CPU_TYPE_ARM64,
        .filetype = QEMU_DARWIN_MH_EXECUTE,
    };
    QemuDarwinEntryPointCommand main_cmd = {
        .cmd = QEMU_DARWIN_LC_MAIN,
        .cmdsize = sizeof(main_cmd),
    };

    return header.magic == QEMU_DARWIN_MH_MAGIC_64 &&
           main_cmd.cmd == QEMU_DARWIN_LC_MAIN ? 0 : 1;
}
"""
    with tempfile.TemporaryDirectory(prefix="whp-darwin-macho-") as tmp:
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
                "-o",
                str(exe),
            ],
            check=True,
        )
        subprocess.run([str(exe)], check=True)

    print("Darwin Mach-O target ABI: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
