#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard QEMU GLib memory-copy migrations without raising the GLib ABI floor.

Run --runtime on a builder with a C compiler and glib-2.0 pkg-config files.
The default static gate also works on build-policy and source-only runners.
"""

import argparse
from pathlib import Path
import re
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SITES = {
    "accel/tcg/cputlb.c": 2,
    "linux-user/uaccess.c": 1,
    "system/vl.c": 1,
    "system/memory.c": 1,
    "qapi/qapi-clone-visitor.c": 8,
}

def static_gate():
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    compat = (ROOT / "include/glib-compat.h").read_text(encoding="utf-8")
    assert "glib_req_ver = '>=2.66.0'" in meson
    assert "#define GLIB_VERSION_MAX_ALLOWED GLIB_VERSION_2_66" in compat
    assert "static inline gpointer g_memdup2_qemu(gconstpointer mem, gsize byte_size)" in compat
    assert "#if GLIB_CHECK_VERSION(2, 68, 0)" in compat
    assert "new_mem = g_malloc(byte_size);" in compat
    assert "memcpy(new_mem, mem, byte_size);" in compat
    assert "#define g_memdup2(m, s) g_memdup2_qemu(m, s)" in compat

    for path, count in SITES.items():
        code = (ROOT / path).read_text(encoding="utf-8")
        assert not re.search(r"\bg_memdup\s*\(", code), path
        assert len(re.findall(r"\bg_memdup2\s*\(", code)) == count, path
    visitor = (ROOT / "qapi/qapi-visit-core.c").read_text(encoding="utf-8")
    assert "g_memdup2() during visit_start_*()" in visitor


def runtime_gate():
    c_source = r"""
#include <stdbool.h>
#include <errno.h>
#include <string.h>
#include <stdlib.h>
#include "glib-compat.h"
int main(void)
{
    const unsigned char source[] = { 0x11, 0x22, 0x33, 0x44 };
    unsigned char *copy = g_memdup2(source, sizeof(source));
    if (!copy || copy == source || memcmp(source, copy, sizeof(source))) {
        return 1;
    }
    copy[0] = 0x55;
    if (source[0] != 0x11 || g_memdup2(NULL, 4) != NULL) {
        g_free(copy);
        return 2;
    }
    g_free(copy);
    return 0;
}
"""
    cflags = shlex.split(subprocess.check_output(
        ["pkg-config", "--cflags", "glib-2.0"], text=True))
    libs = shlex.split(subprocess.check_output(
        ["pkg-config", "--libs", "glib-2.0"], text=True))
    with tempfile.TemporaryDirectory(prefix="qemu-glib-memdup-") as directory:
        file = Path(directory) / "smoke.c"
        binary = Path(directory) / "smoke"
        file.write_text(c_source, encoding="utf-8")
        subprocess.run(
            ["cc", "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             "-I", str(ROOT / "include"), *cflags, str(file),
             "-o", str(binary), *libs], check=True)
        subprocess.run([str(binary)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true",
                        help="also compile and run an actual GLib copy test")
    args = parser.parse_args()
    static_gate()
    if args.runtime:
        runtime_gate()
    print("GLib g_memdup2 compatibility and memory-copy checks passed")


if __name__ == "__main__":
    main()
