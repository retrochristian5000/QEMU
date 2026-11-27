#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the real PIT timing helpers without scheduling a full VM."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
COMMON = ROOT / "hw/timer/i8254_common.c"
EMULATED = ROOT / "hw/timer/i8254.c"
INTERNAL = ROOT / "include/hw/timer/i8254_internal.h"

STUBS = r"""
#include <assert.h>
#include <stdint.h>
#include <stddef.h>
#include <stdbool.h>

#define PIT_FREQ 1193182U
#define NANOSECONDS_PER_SECOND 1000000000ULL
#define QEMU_ALIGN_DOWN(n, m) ((n) / (m) * (m))

typedef struct PITChannelState {
    int count;
    uint8_t mode;
    uint8_t gate;
    int64_t count_load_time;
} PITChannelState;

static inline uint8_t pit_effective_mode(const PITChannelState *s)
{
    return s->mode >= 6 ? s->mode - 4 : s->mode;
}

static unsigned int muldiv_calls;
static uint64_t muldiv64(uint64_t value, uint32_t mul, uint32_t div)
{
    muldiv_calls++;
    /* All test timestamps are below one second: multiplication fits. */
    assert(value <= 1000000000ULL);
    return value * mul / div;
}
static uint64_t muldiv64_round_up(uint64_t value, uint32_t mul, uint32_t div)
{
    muldiv_calls++;
    assert(value <= 1000000000ULL);
    return (value * mul + div - 1) / div;
}
"""

CASES = r"""
static void check_case(PITChannelState *state, int64_t now)
{
    int expected_out, paired_out;
    int64_t expected_next, paired_next;

    muldiv_calls = 0;
    expected_out = pit_get_out(state, now);
    expected_next = pit_get_next_transition_time(state, now);
    unsigned int separate_muldivs = muldiv_calls;

    muldiv_calls = 0;
    pit_get_irq_timing(state, now, &paired_out, &paired_next);
    /* Both paths still convert the next PIT tick back to nanoseconds. */
    assert(muldiv_calls + 1 == separate_muldivs);
    assert(paired_out == expected_out);
    assert(paired_next == expected_next);
    assert(paired_out == 0 || paired_out == 1);
    assert(paired_next == -1 || paired_next > now);
}

static int64_t ns_for_ticks(uint64_t ticks)
{
    return (ticks * NANOSECONDS_PER_SECOND + PIT_FREQ - 1) / PIT_FREQ;
}

int main(void)
{
    static const int counts[] = { 2, 3, 5, 1000, 1193, 65536 };
    static const int64_t times[] = {
        0, 1, 500, 1000, 10000, 100000,
        1000000, 10000000, 100000000, 750000000
    };
    PITChannelState s = { .gate = 1 };

    for (unsigned mode = 0; mode < 6; ++mode) {
        for (unsigned c = 0; c < sizeof(counts) / sizeof(counts[0]); ++c) {
            s.mode = mode;
            s.count = counts[c];
            s.count_load_time = 0;
            for (unsigned t = 0; t < sizeof(times) / sizeof(times[0]); ++t) {
                check_case(&s, times[t]);
            }
            check_case(&s, ns_for_ticks(s.count - 1));
            check_case(&s, ns_for_ticks(s.count));
            check_case(&s, ns_for_ticks(s.count + 1));
        }
    }

    /* Mode 3 odd divider: high for ceil(N/2), low for floor(N/2). */
    s.mode = 3;
    s.count = 5;
    assert(pit_get_out(&s, ns_for_ticks(0)) == 1);
    assert(pit_get_out(&s, ns_for_ticks(2)) == 1);
    assert(pit_get_out(&s, ns_for_ticks(3)) == 0);
    assert(pit_get_out(&s, ns_for_ticks(5)) == 1);

    /* Mode 2 has one low clock per period. */
    s.mode = 2;
    assert(pit_get_out(&s, ns_for_ticks(4)) == 0);
    assert(pit_get_out(&s, ns_for_ticks(5)) == 1);
    assert(pit_get_out(&s, ns_for_ticks(6)) == 1);

    /* Modes 4/5: check polarity relative to the existing load epoch. */
    for (unsigned mode = 4; mode <= 5; mode++) {
        s.mode = mode;
        assert(pit_get_out(&s, ns_for_ticks(0)) == 1);
        assert(pit_get_out(&s, ns_for_ticks(4)) == 1);
        assert(pit_get_out(&s, ns_for_ticks(5)) == 0);
        assert(pit_get_out(&s, ns_for_ticks(6)) == 1);
        assert(pit_get_next_transition_time(&s, ns_for_ticks(6)) == -1);
    }

    return 0;
}
"""


class PITTimingTests(unittest.TestCase):
    def test_single_elapsed_conversion_and_deadlines(self) -> None:
        src = COMMON.read_text(encoding="utf-8")
        start = src.index("static uint64_t pit_elapsed_ticks(")
        end = src.index("\nvoid pit_get_channel_info_common(", start)
        implementation = src[start:end]

        cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(cc, "a native C compiler is required")
        with tempfile.TemporaryDirectory(prefix="qemu-pit-irq-") as tmp:
            c_path = Path(tmp) / "test.c"
            executable = Path(tmp) / "test"
            c_path.write_text(STUBS + "\n" + implementation + "\n" + CASES,
                              encoding="utf-8")
            # Existing PIT code mixes unsigned ticks with signed counts.
            # Keep its original arithmetic untouched during this hot-path test.
            subprocess.run([cc, "-std=gnu11", "-Wall", "-Wextra",
                            "-Werror", "-Wno-sign-compare",
                            str(c_path), "-o", str(executable)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(executable)], check=True)

    def test_consumer_and_existing_apis(self) -> None:
        emu = EMULATED.read_text(encoding="utf-8")
        common = COMMON.read_text(encoding="utf-8")
        internal = INTERNAL.read_text(encoding="utf-8")

        self.assertIn(
            "pit_get_irq_timing(s, current_time, &irq_level, &expire_time);",
            emu,
        )
        self.assertIn("int pit_get_out(PITChannelState *s,", common)
        self.assertIn("int64_t pit_get_next_transition_time(", common)
        self.assertIn("void pit_get_irq_timing(PITChannelState *s,", internal)
        self.assertIn("timer_mod(s->irq_timer, expire_time);", emu)
        self.assertIn("qemu_set_irq(s->irq, irq_level);", emu)


if __name__ == "__main__":
    unittest.main()
