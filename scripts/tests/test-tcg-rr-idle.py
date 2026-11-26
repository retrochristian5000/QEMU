#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Test real TCG round-robin idle-timer policy with stubbed CPU states."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "accel" / "tcg" / "tcg-accel-ops-rr.c"

STUBS = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

typedef struct CPUState {
    struct CPUState *next;
    bool runnable;
    bool idle;
} CPUState;
typedef struct QEMUTimer { bool pending; } QEMUTimer;

static CPUState *first_cpu;
#define CPU_NEXT(cpu) ((cpu)->next)
#define QEMU_CLOCK_VIRTUAL 1

static QEMUTimer timer_storage;
static QEMUTimer *rr_kick_vcpu_timer;
static int timers_created, timer_arms, timer_cancels;

static int64_t rr_next_kick_time(void) { return 500; }
static void rr_kick_thread(void *opaque) { (void)opaque; }

static QEMUTimer *timer_new_ns(int clock, void (*fn)(void *), void *opaque)
{
    assert(clock == QEMU_CLOCK_VIRTUAL);
    assert(fn == rr_kick_thread);
    assert(opaque == NULL);
    timers_created++;
    return &timer_storage;
}

static bool timer_pending(QEMUTimer *timer) { return timer->pending; }
static void timer_mod(QEMUTimer *timer, int64_t expiration)
{
    assert(expiration == 500 && !timer->pending);
    timer->pending = true;
    timer_arms++;
}
static void timer_del(QEMUTimer *timer)
{
    assert(timer->pending);
    timer->pending = false;
    timer_cancels++;
}
"""

CASES = r"""
int main(void)
{
    CPUState primary = { .runnable = true };
    CPUState secondary = { .runnable = true, .idle = true };

    /* Only one vCPU: no periodic preemption is necessary. */
    first_cpu = &primary;
    rr_start_kick_timer();
    assert(timers_created == 0 && !rr_kick_vcpu_timer);

    /*
     * Two present, but one is halted. Keep the timer armed: an interrupt
     * from the running vCPU can wake its sibling without kicking the
     * shared host thread out of the current translated block chain.
     */
    primary.next = &secondary;
    rr_start_kick_timer();
    assert(timers_created == 1 && timer_arms == 1);
    assert(timer_storage.pending);

    /* A wakeup does not need to rearm an already pending timer. */
    secondary.idle = false;
    rr_start_kick_timer();
    assert(timers_created == 1 && timer_arms == 1);

    /* A halted or stopped sibling must not disable periodic preemption. */
    secondary.idle = true;
    secondary.runnable = false;
    rr_start_kick_timer();
    assert(timer_storage.pending && timer_cancels == 0);

    /* The all-idle wait path explicitly stops the timer. */
    primary.idle = true;
    rr_stop_kick_timer();
    assert(!timer_storage.pending && timer_cancels == 1);
    rr_stop_kick_timer();
    assert(timer_cancels == 1);

    /* Any wakeup re-arms the existing timer before execution resumes. */
    primary.idle = false;
    rr_start_kick_timer();
    assert(timer_storage.pending && timer_arms == 2);
    assert(timers_created == 1);

    /* Removing the secondary CPU restores the single-vCPU fast path. */
    primary.next = NULL;
    rr_start_kick_timer();
    assert(!timer_storage.pending && timer_cancels == 2);
    return 0;
}
"""


class RoundRobinIdleTests(unittest.TestCase):
    def test_present_cpu_timer_arbitration(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("static bool rr_needs_kick_timer(void)")
        end = source.index("\nstatic void rr_wait_io_event(void)", start)
        implementation = source[start:end]
        compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "native C compiler required")

        with tempfile.TemporaryDirectory(prefix="tcg-rr-idle-") as work:
            c_file = Path(work) / "test.c"
            binary = Path(work) / "test"
            c_file.write_text(STUBS + "\n" + implementation + "\n" + CASES,
                              encoding="utf-8")
            subprocess.run([compiler, "-std=c11", "-Wall", "-Wextra",
                            "-Werror", str(c_file), "-o", str(binary)],
                           check=True, capture_output=True, text=True)
            subprocess.run([str(binary)], check=True)

    def test_event_driven_hlt_and_irq_wakeup_remains_intact(self):
        source = SOURCE.read_text(encoding="utf-8")
        self.assertIn("qemu_cond_wait_bql(first_cpu->halt_cond)", source)
        self.assertIn("while (all_cpu_threads_idle()) {\n"
                      "        rr_stop_kick_timer();", source)
        self.assertIn("rr_kick_vcpu_thread(CPUState *unused)", source)
        self.assertIn("tcg_kick_vcpu_thread(cpu)", source)


if __name__ == "__main__":
    unittest.main()
