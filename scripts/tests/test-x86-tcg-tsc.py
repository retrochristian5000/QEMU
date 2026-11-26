#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the actual x86 system TSC helper with synthetic virtual time."""

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[2] / "hw/i386/x86-cpu.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>

typedef struct CPUX86State {
    int64_t tsc_khz;
} CPUX86State;

static bool tcg;
static int64_t now, elapsed;
static bool tcg_enabled(void) { return tcg; }
static int64_t cpus_get_virtual_clock(void) { return now; }
static int64_t cpus_get_elapsed_ticks(void) { return elapsed; }

static uint64_t muldiv64(uint64_t a, uint32_t b, uint32_t c)
{
    return (__uint128_t)a * b / c;
}
"""

CASES = r"""
int main(void)
{
    CPUX86State cpu[4] = {{200000}, {200000}, {200000}, {200000}};
    elapsed = 987654321;
    now = 1000000000;

    /* Other accelerators retain their previous source. */
    assert(cpu_get_tsc(&cpu[0]) == (uint64_t)elapsed);
    tcg = true;
    for (unsigned int i = 0; i < 4; i++) {
        assert(cpu_get_tsc(&cpu[i]) == 200000000);
    }
    now += 1000000;
    assert(cpu_get_tsc(&cpu[0]) == 200200000);
    assert(cpu_get_tsc(&cpu[3]) == 200200000);

    /* One tick every five nanoseconds, including fractional intervals. */
    now = 4;
    assert(cpu_get_tsc(&cpu[0]) == 0);
    now = 5;
    assert(cpu_get_tsc(&cpu[0]) == 1);

    /* Unconfigured frequency retains the historical tick source. */
    cpu[0].tsc_khz = 0;
    assert(cpu_get_tsc(&cpu[0]) == (uint64_t)elapsed);

    /* A long-running clock and a rate above the 32-bit kHz range. */
    now = INT64_MAX;
    cpu[0].tsc_khz = INT64_MAX / 1000;
    assert(cpu_get_tsc(&cpu[0]) ==
           (uint64_t)((__uint128_t)now * cpu[0].tsc_khz / 1000000));
    return 0;
}
"""


class TSCTests(unittest.TestCase):
    def test_configured_frequency(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("uint64_t cpu_get_tsc(")
        end = source.index("\n/* IRQ handling */", start)
        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(cc, "native C compiler required")
        with tempfile.TemporaryDirectory(prefix="qemu-x86-tsc-") as work:
            src = Path(work) / "test.c"
            binary = Path(work) / "test"
            src.write_text(STUBS + source[start:end] + CASES, encoding="utf-8")
            subprocess.run([cc, "-std=c11", "-Wall", "-Wextra", "-Werror",
                            str(src), "-o", str(binary)], check=True)
            subprocess.run([str(binary)], check=True)


if __name__ == "__main__":
    unittest.main()
