#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the real UI-info update function with a minimal C timer stub."""

from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "ui" / "console.c"

STUB = r"""
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <string.h>

typedef struct {
    uint32_t width;
    uint32_t height;
    uint32_t refresh_rate;
} QemuUIInfo;

typedef struct {
    QemuUIInfo ui_info;
    void *ui_timer;
    bool supported;
} QemuConsole;

#define QEMU_CLOCK_REALTIME 1

static int timer_updates;
static int64_t last_timer_deadline = -1;

static bool qemu_console_ui_info_supported(const QemuConsole *con)
{
    return con != NULL && con->supported;
}

static int64_t qemu_clock_get_ms(int type)
{
    assert(type == QEMU_CLOCK_REALTIME);
    return 125;
}

static void timer_mod(void *timer, int64_t deadline)
{
    (void)timer;
    timer_updates++;
    last_timer_deadline = deadline;
}
"""

CHECKS = r"""
int main(void)
{
    QemuConsole con = { .supported = true };
    QemuUIInfo first = { .width = 640, .height = 480 };
    QemuUIInfo resize = { .width = 800, .height = 600 };
    QemuUIInfo immediate = { .width = 1024, .height = 768 };
    QemuUIInfo incomplete = { .width = 640 };
    QemuConsole other = { .supported = true };

    assert(qemu_console_set_ui_info(NULL, &first, true) == -1);
    assert(timer_updates == 0);

    /* A real first frame is announced without a one-second startup wait. */
    assert(qemu_console_set_ui_info(&con, &first, true) == 0);
    assert(timer_updates == 1);
    assert(last_timer_deadline == 125);
    assert(con.ui_info.width == 640);

    /* Unchanged information must not reset the display timer. */
    assert(qemu_console_set_ui_info(&con, &first, true) == 0);
    assert(timer_updates == 1);

    /* Subsequent user-driven resizes retain the one-second debounce. */
    assert(qemu_console_set_ui_info(&con, &resize, true) == 0);
    assert(timer_updates == 2);
    assert(last_timer_deadline == 1125);

    /* A caller which explicitly disables delay still updates at once. */
    assert(qemu_console_set_ui_info(&con, &immediate, false) == 0);
    assert(timer_updates == 3);
    assert(last_timer_deadline == 125);

    /* Partial initial display measurements are not treated as resizes. */
    assert(qemu_console_set_ui_info(&other, &incomplete, true) == 0);
    assert(last_timer_deadline == 125);
    assert(qemu_console_set_ui_info(&other, &first, true) == 0);
    assert(last_timer_deadline == 125);

    other.supported = false;
    assert(qemu_console_set_ui_info(&other, &resize, true) == -1);
    assert(timer_updates == 5);
    return 0;
}
"""


class DisplayStartupDelayTests(unittest.TestCase):
    def test_initial_ui_info_does_not_wait_for_resize_debounce(self):
        source = SOURCE.read_text(encoding="utf-8")
        start = source.index("int qemu_console_set_ui_info(")
        end = source.index("\n}\n\nvoid qemu_console_update(", start) + 2
        implementation = source[start:end]
        compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
        self.assertIsNotNone(compiler, "native C compiler required")

        with tempfile.TemporaryDirectory(prefix="ui-startup-") as temp:
            directory = Path(temp)
            harness = directory / "test-ui-info.c"
            executable = directory / "test-ui-info"
            harness.write_text(
                STUB + "\n" + implementation + "\n" + CHECKS,
                encoding="utf-8",
            )
            subprocess.run(
                [compiler, "-std=c11", "-Wall", "-Wextra", "-Werror",
                 str(harness), "-o", str(executable)],
                check=True, capture_output=True, text=True,
            )
            subprocess.run([str(executable)], check=True)


if __name__ == "__main__":
    unittest.main()
