#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Run a local program under fork-built LLDB and retain crash diagnostics.

LLDB owns the process from launch, so this never attaches to a protected
Apple process or attempts to call a debugger from an ASan signal handler.
Use --lldb /path/to/fork/bin/lldb -- command [args...].
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile


CRASH_COMMANDS = (
    "thread list",
    "thread backtrace all",
    "frame info",
    "register read pc lr fp sp x8 x16 x17 x22",
    "disassemble --pc --count 24",
    "image list -o -f",
)


def lldb_command(lldb: Path, program: list[str]) -> list[str]:
    # --no-lldbinit keeps user/.cwd commands from silently changing the test.
    # The crash hooks run only when LLDB stops on a crashing target; a normal
    # run still exits without inspecting register state.
    command = [str(lldb), "--no-lldbinit", "--batch",
               "--one-line", "run"]
    for diagnostic in CRASH_COMMANDS:
        command.extend(["--one-line-on-crash", diagnostic])
    return [*command, "--", *program]


def capture(
    lldb: Path, program: list[str], label: str, report_dir: Path | None,
    timeout: int, environ: dict[str, str] | None = None,
) -> tuple[int, Path]:
    if not lldb.is_file():
        raise RuntimeError(f"requested LLDB does not exist: {lldb}")
    if not os.access(lldb, os.X_OK):
        raise RuntimeError(f"requested LLDB is not executable: {lldb}")
    if not program:
        raise RuntimeError("missing executable for LLDB")
    if timeout <= 0:
        raise RuntimeError("LLDB timeout must be positive")

    if report_dir is None:
        report_dir = Path(tempfile.mkdtemp(prefix="whp-lldb-crash-"))
    else:
        report_dir.mkdir(mode=0o700, parents=True, exist_ok=True)

    safe_label = re.sub(r"[^A-Za-z0-9_.-]", "_", label)[:64] or "crash"
    fd, filename = tempfile.mkstemp(prefix=safe_label + "-", suffix=".log",
                                   dir=report_dir)
    report = Path(filename)
    command = lldb_command(lldb, program)
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, check=False,
            env=environ, timeout=timeout,
        )
        output = result.stdout + "\n" + result.stderr
        # LLDB can return success after the debuggee exits unsuccessfully.
        exited = re.search(r"exited with status = ([0-9]+)", output)
        failed = (result.returncode != 0 or
                  bool(re.search(r"stop reason = (?:EXC_|SIG|signal)", output)) or
                  (exited is not None and int(exited.group(1)) != 0))
        status = 1 if failed else 0
        explanation = f"lldb exit={result.returncode}; target_failed={failed}\n"
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"")
        error = (exc.stderr or b"")
        if isinstance(output, bytes):
            output = output.decode("utf-8", errors="replace")
        if isinstance(error, bytes):
            error = error.decode("utf-8", errors="replace")
        output += "\n" + error
        status = 1
        explanation = f"lldb timed out after {timeout}s; debugger stopped\n"

    try:
        with os.fdopen(fd, "w", encoding="utf-8", errors="replace") as log:
            log.write(f"WHP fork LLDB autopsy ({safe_label})\n")
            log.write(explanation)
            log.write(output)
    except BaseException:
        # mkstemp descriptors must not leak even if writing fails.
        try:
            os.close(fd)
        except OSError:
            pass
        raise
    return status, report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lldb", type=Path, required=True,
                        help="absolute path to fork-built lldb (no silent Apple fallback)")
    parser.add_argument("--report-dir", type=Path,
                        help="persistent local directory; private temp dir if omitted")
    parser.add_argument("--label", default="crash")
    parser.add_argument("--timeout", type=int, default=75)
    parser.add_argument("program", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    program = args.program
    if program and program[0] == "--":
        program = program[1:]
    if not program:
        parser.error("provide executable and arguments after --")
    try:
        status, report = capture(
            args.lldb, program, args.label, args.report_dir, args.timeout
        )
    except (OSError, RuntimeError) as exc:
        print(f"error: WHP LLDB autopsy: {exc}", file=sys.stderr)
        return 2
    print(f"WHP LLDB report: {report}")
    return status


if __name__ == "__main__":
    raise SystemExit(main())
