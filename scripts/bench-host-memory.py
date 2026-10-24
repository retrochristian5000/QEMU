#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure QEMU host RSS at paused startup, during boot, and at exit.

Unlike the x86-only BIOS benchmark, this uses QMP and can profile Mac99/PPC
without needing a custom guest image.  It measures the actual process, not
configured guest RAM or the virtual size of the JIT mappings.  An unbooted
firmware workload is NOT a proxy for an OS that has touched all guest RAM.
Linux and macOS report ps RSS in KiB; wait4 ru_maxrss uses KiB on Linux and
bytes on macOS.  Host RSS is not the same as unique physical footprint.
"""

from __future__ import annotations

import argparse
import json
import os
import re
from pathlib import Path
import selectors
import signal
import statistics
import subprocess
import sys
import tempfile
import time


def rss_mib(pid: int) -> float:
    result = subprocess.run(["ps", "-o", "rss=", "-p", str(pid)],
                            check=True, capture_output=True, text=True)
    value = result.stdout.strip()
    if not value or not value.isdecimal():
        raise RuntimeError(f"cannot read RSS for QEMU pid {pid}: {value!r}")
    return int(value) / 1024


def peak_rss_mib(ru_maxrss: int) -> float:
    return ru_maxrss / (1024 * 1024 if sys.platform == "darwin" else 1024)


class QMP:
    def __init__(self, process: subprocess.Popen[bytes]):
        self.process = process
        self.buffer = bytearray()
        self.selector = selectors.DefaultSelector()
        assert process.stdout is not None
        self.selector.register(process.stdout, selectors.EVENT_READ)

    def close(self) -> None:
        self.selector.close()

    def read(self, timeout: float) -> dict:
        deadline = time.monotonic() + timeout
        while True:
            newline = self.buffer.find(b"\n")
            if newline >= 0:
                payload = bytes(self.buffer[:newline]).strip()
                del self.buffer[:newline + 1]
                if payload:
                    return json.loads(payload)
            remaining = deadline - time.monotonic()
            if remaining <= 0 or not self.selector.select(remaining):
                raise TimeoutError("QMP did not respond before timeout")
            assert self.process.stdout is not None
            chunk = os.read(self.process.stdout.fileno(), 65536)
            if not chunk:
                raise RuntimeError("QEMU closed QMP before responding")
            self.buffer.extend(chunk)

    def command(self, name: str, timeout: float) -> dict:
        assert self.process.stdin is not None
        request = {"execute": name, "id": name}
        self.process.stdin.write(json.dumps(request).encode() + b"\n")
        self.process.stdin.flush()
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(f"QMP command {name!r} timed out")
            response = self.read(remaining)
            if response.get("id") == name:
                if "error" in response:
                    raise RuntimeError(f"QMP {name}: {response['error']}")
                if "return" not in response:
                    raise RuntimeError(f"QMP {name} returned no result")
                return response["return"]
            # Events are asynchronous and do not complete the command.


def parse_jit_stats(report: str) -> tuple[int, int, int, int]:
    """Read the fork's live TCG code use, capacity and flush counters."""
    code = re.search(r"^gen code size\s+(\d+)/(\d+)\s*$",
                     report, re.MULTILINE)
    blocks = re.search(r"^TB count\s+(\d+)\s*$", report, re.MULTILINE)
    flushes = re.search(r"^TB flush count\s+(\d+)\s*$",
                        report, re.MULTILINE)
    if not all((code, blocks, flushes)):
        raise RuntimeError("x-query-jit did not report TCG cache/flush counters")
    used, capacity = (int(v) for v in code.groups())
    if capacity == 0 or used > capacity:
        raise RuntimeError("x-query-jit reported an invalid TCG code capacity")
    return used, capacity, int(blocks.group(1)), int(flushes.group(1))


def read_jit_stats(qmp: QMP, timeout: float) -> tuple[int, int, int, int]:
    response = qmp.command("x-query-jit", timeout)
    if not isinstance(response, dict) or not isinstance(
            response.get("human-readable-text"), str):
        raise RuntimeError("x-query-jit returned no human-readable-text")
    return parse_jit_stats(response["human-readable-text"])


def jit_summary(stats: tuple[int, int, int, int]) -> str:
    used, capacity, blocks, flushes = stats
    return (f"JIT code={used / 1048576:.2f}/{capacity / 1048576:.2f} MiB "
            f"({100 * used / capacity:.1f}% used), "
            f"TBs={blocks}, TB flushes={flushes}")


def reap(pid: int, timeout: float) -> tuple[int, float]:
    deadline = time.monotonic() + timeout
    while True:
        waited, status, usage = os.wait4(pid, os.WNOHANG)
        if waited:
            return os.waitstatus_to_exitcode(status), peak_rss_mib(usage.ru_maxrss)
        if time.monotonic() >= deadline:
            raise TimeoutError("QEMU did not exit after QMP quit")
        time.sleep(0.02)


def measure(command: list[str], boot_seconds: float,
            timeout: float, jit_stats: bool = False
            ) -> tuple[float, float, float, tuple[int, int, int, int] | None]:
    with tempfile.TemporaryFile(mode="w+t") as errors:
        process = subprocess.Popen(command, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=errors)
        qmp = QMP(process)
        reaped = False
        try:
            greeting = qmp.read(timeout)
            if "QMP" not in greeting:
                raise RuntimeError(f"expected QMP greeting: {greeting}")
            qmp.command("qmp_capabilities", timeout)
            paused = rss_mib(process.pid)
            qmp.command("cont", timeout)
            time.sleep(boot_seconds)
            running = rss_mib(process.pid)
            jit = read_jit_stats(qmp, timeout) if jit_stats else None
            qmp.command("quit", timeout)
            status, peak = reap(process.pid, timeout)
            reaped = True
            process.returncode = status
            if status != 0:
                raise RuntimeError(f"QEMU exited with status {status}")
            return paused, running, peak, jit
        except Exception as exc:
            errors.seek(0)
            diagnostic = errors.read(4096).strip()
            if diagnostic:
                raise RuntimeError(f"{exc}; QEMU stderr: {diagnostic}") from exc
            raise
        finally:
            qmp.close()
            if not reaped:
                # Popen.kill() can poll/reap the child before wait4(), losing
                # the exit status (and raising ChildProcessError on macOS).
                # Send the signal directly, then reap exactly once via wait4().
                try:
                    os.kill(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass  # Child already exited but still needs reaping.
                _, status, _ = os.wait4(process.pid, 0)
                process.returncode = os.waitstatus_to_exitcode(status)
            if process.stdin is not None:
                process.stdin.close()
            if process.stdout is not None:
                process.stdout.close()


def qemu_command(qemu: str, machine: str, guest_mib: int, smp: int,
                 tb_mib: int | None, split_wx: str, nodefaults: bool) -> list[str]:
    accel = "tcg"
    if tb_mib is not None:
        accel += f",tb-size={tb_mib}"
    if split_wx != "auto":
        accel += f",split-wx={split_wx}"
    command = [qemu, "-machine", machine, "-accel", accel,
               "-m", f"{guest_mib}M", "-smp", str(smp),
               "-display", "none", "-monitor", "none", "-serial", "none",
               "-qmp", "stdio", "-S", "-no-reboot"]
    if nodefaults:
        command.append("-nodefaults")
    return command


def self_test() -> None:
    assert qemu_command("qemu", "mac99", 256, 1, 32, "on", True) == [
        "qemu", "-machine", "mac99", "-accel", "tcg,tb-size=32,split-wx=on",
        "-m", "256M", "-smp", "1", "-display", "none", "-monitor", "none",
        "-serial", "none", "-qmp", "stdio", "-S", "-no-reboot", "-nodefaults"]
    fake = '''import json, sys
print(json.dumps({"QMP": {"version": {}}}), flush=True)
for line in sys.stdin:
    message = json.loads(line)
    print(json.dumps({"return": {}, "id": message["id"]}), flush=True)
    if message["execute"] == "quit":
        break
'''
    paused, running, peak, jit = measure([sys.executable, "-u", "-c", fake],
                                         0.02, 10)
    assert jit is None
    assert 0 < paused and 0 < running and peak >= min(paused, running)
    fixture = ("Translation buffer state:\n"
               "gen code size       1024/65536\n"
               "TB count            12\n"
               "Statistics:\nTB flush count      2\n")
    assert parse_jit_stats(fixture) == (1024, 65536, 12, 2)
    class FakeJitQMP:
        def command(self, name: str, timeout: float) -> dict:
            assert name == "x-query-jit" and timeout == 1
            return {"human-readable-text": fixture}
    assert read_jit_stats(FakeJitQMP(), 1) == (1024, 65536, 12, 2)
    try:
        parse_jit_stats("gen code size 1024/65536\nTB count 12\n")
    except RuntimeError:
        pass
    else:
        raise AssertionError("incomplete TCG statistics must fail")
    failed = '''import sys
sys.stderr.write("controlled QEMU failure\\n")
sys.exit(4)
'''
    try:
        measure([sys.executable, "-c", failed], 0.0, 2)
    except RuntimeError as error:
        assert "controlled QEMU failure" in str(error)
    else:
        raise AssertionError("failed child must not count as a measurement")
    print("Host RSS/QMP handshake, exit accounting and failure checks passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-ppc")
    parser.add_argument("--machine", default="mac99")
    parser.add_argument("--guest-mib", type=int, default=256)
    parser.add_argument("--cpus", type=int, default=1)
    parser.add_argument("--tb-size", type=int, metavar="MiB")
    parser.add_argument("--split-wx", choices=("auto", "on", "off"),
                        default="auto")
    parser.add_argument("--nodefaults", action="store_true")
    parser.add_argument("--boot-seconds", type=float, default=2.0)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--jit-stats", action="store_true",
                        help="also query TCG code use, capacity and flushes")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if sys.platform not in ("darwin", "linux") or not hasattr(os, "wait4"):
        parser.error("this benchmark requires macOS or Linux with wait4(2)")
    if args.self_test:
        self_test()
        return 0
    if args.guest_mib <= 0 or args.cpus <= 0 or args.rounds <= 0:
        parser.error("guest RAM, CPU count and rounds must be positive")
    if args.tb_size is not None and args.tb_size < 1:
        parser.error("--tb-size must be at least 1 MiB")
    if args.boot_seconds < 0 or args.timeout <= 0:
        parser.error("boot time must not be negative and timeout must be positive")
    candidate = Path(args.qemu)
    if candidate.exists():
        qemu = str(candidate.resolve())
    else:
        import shutil
        qemu = shutil.which(args.qemu)
        if not qemu:
            parser.error(f"QEMU executable not found: {args.qemu}")
    command = qemu_command(qemu, args.machine, args.guest_mib, args.cpus,
                           args.tb_size, args.split_wx, args.nodefaults)
    print(f"Host RSS for {args.machine}: guest={args.guest_mib} MiB, "
          f"cpus={args.cpus}, tb={args.tb_size or 'auto'}, "
          f"split-wx={args.split_wx}")
    print("round    paused_MiB   running_MiB   peak_MiB   boot_delta_MiB")
    samples = []
    for round_number in range(1, args.rounds + 1):
        values = measure(command, args.boot_seconds, args.timeout,
                         args.jit_stats)
        paused, running, peak, jit = values
        print(f"{round_number:5} {paused:13.1f} {running:13.1f} "
              f"{peak:10.1f} {running - paused:16.1f}")
        samples.append(values)
        if jit is not None:
            print("      " + jit_summary(jit))
    paused, running, peak = [statistics.median(column)
                             for column in zip(*(s[:3] for s in samples))]
    print(f"median {paused:13.1f} {running:13.1f} "
          f"{peak:10.1f} {running - paused:16.1f}")
    if args.jit_stats:
        snapshots = [s[3] for s in samples]
        medians = tuple(int(statistics.median(column))
                        for column in zip(*snapshots))
        print("median " + jit_summary(medians))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
