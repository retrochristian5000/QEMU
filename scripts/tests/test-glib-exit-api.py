#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard GLib exit deprecations and the simple trace shutdown contract.

Standard C atexit() remains valid for program-lifetime callbacks.  Do not
substitute QEMU's system-only exit notifier for the shared trace backend,
which is also initialized by non-system QEMU executables.
"""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]

trace = (ROOT / "trace/simple.c").read_text(encoding="utf-8")
control = (ROOT / "trace/control.c").read_text(encoding="utf-8")
system = (ROOT / "system/vl.c").read_text(encoding="utf-8")
runstate = (ROOT / "system/runstate.c").read_text(encoding="utf-8")

# GLib's g_atexit(), g_ATEXIT(), and ATEXIT() macros are deprecated.  Their
# names must not be reintroduced in compiled sources, including C++.
result = subprocess.run(
    ["git", "-C", str(ROOT), "grep", "-n", "-E",
     r"(^|[^[:alnum:]_])(g_atexit|g_ATEXIT|ATEXIT)[[:space:]]*\\(",
     "--", "*.c", "*.h", "*.cc", "*.cpp"],
    text=True, capture_output=True,
)
if result.returncode not in (0, 1):
    raise RuntimeError(result.stderr)
assert result.returncode == 1, result.stdout

start = trace.index("bool st_init(void)")
body = trace[start:trace.index("void st_init_group(", start)]
thread_start = body.index("thread = trace_thread_create(writeout_thread);")
registration = body.index("if (atexit(st_flush_trace_buffer) != 0) {")
assert thread_start < registration
assert 'warn_report("unable to register simple trace backend exit flush");' in body
assert "return false;" in body[registration:]
assert "return true;" in body[registration:]
assert "flush_trace_file(true);" in trace
assert "if (!st_init()) {" in control

# Simple tracing is set up after daemonizing because its atexit hook must not
# try to wait on a worker that disappeared in the forked parent.
assert system.index("qemu_maybe_daemonize(pid_file);") < system.index(
    "if (!trace_init_backends()) {"
)
# QEMU's exit notifier is intentionally preserved for system-executable users.
assert "qemu_add_exit_notifier(Notifier *notify)" in runstate
assert "atexit(qemu_run_exit_notifiers);" in runstate

print("GLib exit deprecation and trace registration contract passed")
