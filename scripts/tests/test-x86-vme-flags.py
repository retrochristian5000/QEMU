#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test the shared VME flag policy without starting a guest."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
HEADER = ROOT / "target/i386/tcg/vme-flags.h"

SOURCE = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

#define TF_MASK 0x100u
#define IF_MASK 0x200u
#define IOPL_MASK 0x3000u
#define NT_MASK 0x4000u
#define VM_MASK 0x20000u
#define VIF_MASK 0x80000u
#define VIP_MASK 0x100000u
#define CR4_VME_MASK 1u
#define CR4_PVI_MASK 2u

#include "vme-flags.h"

int main(void)
{
    for (uint32_t cr4 = 0; cr4 < 4; cr4++) {
        for (unsigned vm = 0; vm < 2; vm++) {
            for (unsigned vip = 0; vip < 2; vip++) {
                uint32_t flags = (vm ? VM_MASK : 0) |
                                 (vip ? VIP_MASK : 0);
                bool enabled = (cr4 & (vm ? 1u : 2u)) != 0;

                assert(vme_if_allowed(cr4, flags, false) == enabled);
                assert(vme_if_allowed(cr4, flags, true) ==
                       (enabled && !vip));
            }
        }
    }

    for (unsigned vif = 0; vif < 2; vif++) {
        for (uint32_t image = 0; image <= 0xffff; image++) {
            uint32_t flags = image | (vif ? VIF_MASK : 0);
            uint32_t pushed = vme_flags_image(flags);

            assert((pushed & IOPL_MASK) == IOPL_MASK);
            assert(!!(pushed & IF_MASK) == vif);
            assert((pushed & ~(IOPL_MASK | IF_MASK)) ==
                   (image & ~(IOPL_MASK | IF_MASK)));
        }
    }

    for (unsigned vip = 0; vip < 2; vip++) {
        for (uint32_t image = 0; image <= 0xffff; image++) {
            uint32_t old = VM_MASK | IF_MASK | VIF_MASK | 0x1000u |
                           (vip ? VIP_MASK : 0);
            uint32_t value = 0xdeadbeefu;
            bool allowed = !(image & TF_MASK) &&
                           !(vip && (image & IF_MASK));

            assert(vme_flags_restore(old, image, &value) == allowed);
            if (allowed) {
                uint32_t mask = TF_MASK | NT_MASK | VIF_MASK;
                uint32_t result = (old & ~mask) | (value & mask);

                assert(!!(result & VIF_MASK) == !!(image & IF_MASK));
                assert((result & (IF_MASK | IOPL_MASK | VM_MASK |
                                  VIP_MASK)) ==
                       (old & (IF_MASK | IOPL_MASK | VM_MASK | VIP_MASK)));
            } else {
                assert(value == 0xdeadbeefu);
            }
        }
    }
    return 0;
}
"""


class VMEFlagTests(unittest.TestCase):
    def test_policy(self):
        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(cc, "native C compiler required")
        with tempfile.TemporaryDirectory(prefix="qemu-vme-flags-") as work:
            source = Path(work) / "test.c"
            binary = Path(work) / "test"
            source.write_text(SOURCE, encoding="utf-8")
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            "-fsanitize=undefined", "-I", str(HEADER.parent),
                            str(source), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
