#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Audit the Sam460ex /cpm FDT removal path and system libfdt probe.

Use --runtime on a build host with libfdt headers and library installed to
confirm fdt_nop_node removes a node without damaging unrelated siblings.
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def source_test():
    sam = (ROOT / "hw/ppc/sam460ex.c").read_text(encoding="utf-8")
    device_tree = (ROOT / "system/device_tree.c").read_text(encoding="utf-8")
    header = (ROOT / "include/system/device_tree.h").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    kconfig = (ROOT / "hw/ppc/Kconfig").read_text(encoding="utf-8")

    assert '#include "system/device_tree.h"' in sam
    assert "#include <libfdt.h>" in sam
    assert 'offset = fdt_path_offset(fdt, "/cpm");' in sam
    assert 'qemu_fdt_nop_node(fdt, "/cpm");' in sam
    assert 'offset != -FDT_ERR_NOTFOUND' in sam
    assert 'fdt_strerror(offset)' in sam
    assert '_FDT(fdt_nop_node(fdt, offset))' not in sam
    assert 'int qemu_fdt_nop_node(void *fdt, const char *node_path);' in header
    assert 'r = fdt_nop_node(fdt, findnode_nofail(fdt, node_path));' in device_tree

    assert "fdt_find_max_phandle(NULL, NULL);" in meson
    assert "return fdt_nop_node(NULL, 0);" in meson
    assert "dependencies: fdt" in meson
    # The library probe is insufficient if the final emulator link drops
    # the dependency after extracting system/device_tree.c from libsystem.
    assert "if 'CONFIG_DEVICE_TREE' in config_target" in meson
    assert "arch_deps += [fdt]" in meson
    assert "dependencies: arch_deps + exe['dependencies']" in meson
    assert 'fdt_nop_mode' not in device_tree
    assert "config SAM460EX\n    bool\n    default y\n    depends on PPC && FDT" in kconfig


def runtime_test():
    code = r"""
#include <libfdt.h>
#include <libfdt_env.h>

int main(void)
{
    char blob[4096] = { 0 };
    int cpm;
    int other;

    if (fdt_create_empty_tree(blob, sizeof(blob)) < 0) {
        return 1;
    }
    other = fdt_add_subnode(blob, 0, "serial");
    cpm = fdt_add_subnode(blob, 0, "cpm");
    if (other < 0 || cpm < 0 ||
        fdt_path_offset(blob, "/cpm") != cpm) {
        return 2;
    }
    if (fdt_nop_node(blob, cpm) < 0) {
        return 3;
    }
    if (fdt_path_offset(blob, "/cpm") != -FDT_ERR_NOTFOUND) {
        return 4;
    }
    if (fdt_path_offset(blob, "/serial") < 0) {
        return 5;
    }
    return 0;
}
"""
    cc = shlex.split(os.environ.get("CC", "cc"))
    with tempfile.TemporaryDirectory(prefix="whp-sam460ex-fdt-") as folder:
        file = Path(folder) / "fdt-nop.c"
        binary = Path(folder) / "fdt-nop"
        file.write_text(code, encoding="utf-8")
        subprocess.run(
            [*cc, "-std=gnu11", "-Wall", "-Wextra", "-Werror",
             str(file), "-o", str(binary), "-lfdt"],
            check=True,
        )
        subprocess.run([str(binary)], check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime", action="store_true",
                        help="compile and run a libfdt node removal smoke test")
    args = parser.parse_args()
    source_test()
    if args.runtime:
        runtime_test()
    print("Sam460ex libfdt node removal contract passed")


if __name__ == "__main__":
    main()
