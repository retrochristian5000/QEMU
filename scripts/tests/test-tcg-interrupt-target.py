#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the real TCG interrupt handler with shared and separate threads."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "accel/tcg/tcg-accel-ops.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct CPUState {
    unsigned int thread;
    unsigned int interrupt_request;
    unsigned int kicks;
    struct {
        struct {
            struct {
                uint16_t high;
            } u16;
        } icount_decr;
    } neg;
} CPUState;

static CPUState *current_cpu;
static unsigned int host_thread;

#define qatomic_set(ptr, val) (*(ptr) = (val))

static void cpu_set_interrupt(CPUState *cpu, int mask)
{
    cpu->interrupt_request |= mask;
}

static bool qemu_cpu_is_self(CPUState *cpu)
{
    return cpu->thread == host_thread;
}

static void qemu_cpu_kick(CPUState *cpu)
{
    cpu->kicks++;
}
"""

CASES = r"""
int main(void)
{
    CPUState cpus[4] = { { .thread = 1 }, { .thread = 1 },
                         { .thread = 1 }, { .thread = 2 } };

    host_thread = 1;
    current_cpu = &cpus[0];

    /* Local interrupt: exit the TB without a redundant scheduler kick. */
    tcg_handle_interrupt(&cpus[0], 1);
    assert(cpus[0].interrupt_request == 1);
    assert(cpus[0].neg.icount_decr.u16.high == UINT16_MAX);
    assert(cpus[0].kicks == 0);

    /* Round-robin siblings share the thread, not the executing CPU. */
    for (unsigned int i = 1; i < 3; i++) {
        tcg_handle_interrupt(&cpus[i], 2);
        assert(cpus[i].interrupt_request == 2);
        assert(cpus[i].kicks == 1);
        assert(cpus[i].neg.icount_decr.u16.high == 0);
    }

    /* MTTCG remote CPU: wake its own thread as before. */
    tcg_handle_interrupt(&cpus[3], 4);
    assert(cpus[3].interrupt_request == 4 && cpus[3].kicks == 1);

    /* I/O thread with no current guest CPU. */
    current_cpu = 0;
    host_thread = 3;
    tcg_handle_interrupt(&cpus[0], 8);
    assert(cpus[0].interrupt_request == 9 && cpus[0].kicks == 1);

    /* Zero mask used for A20 changes must still request an exit. */
    current_cpu = &cpus[0];
    host_thread = 1;
    cpus[0].neg.icount_decr.u16.high = 0;
    tcg_handle_interrupt(&cpus[0], 0);
    assert(cpus[0].interrupt_request == 9 && cpus[0].kicks == 1);
    assert(cpus[0].neg.icount_decr.u16.high == UINT16_MAX);
    return 0;
}
"""


class InterruptTargetTests(unittest.TestCase):
    def test_interrupt_target(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("void tcg_handle_interrupt(")
        end = source.index("\n/* Translate GDB", start)
        implementation = source[start:end]
        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(cc, "native C compiler required")
        with tempfile.TemporaryDirectory(prefix="qemu-tcg-irq-") as work:
            src = Path(work) / "test.c"
            binary = Path(work) / "test"
            src.write_text(STUBS + implementation + CASES, encoding="utf-8")
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(src), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
