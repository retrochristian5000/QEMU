#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Measure host peak RSS as x86 TCG guest SMP capacity increases.

Uses the deterministic real-mode BIOS from bench-i386-tcg.py. Only the
bootstrap CPU runs the BIOS workload; other vCPUs are created but not
given an AP startup sequence. Results measure startup/per-vCPU overhead,
NOT memory pressure under a workload running on every CPU.

Peak resident memory comes from wait4(2) for each child, rather than from
system-wide counters or a sampling interval that can miss short processes.
Darwin reports ru_maxrss in bytes; Linux reports KiB.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import runpy
import statistics
import subprocess
import sys
import tempfile
import time


def peak_rss_mib(ru_maxrss: int) -> float:
    if sys.platform == "darwin":
        return ru_maxrss / (1024 * 1024)
    if sys.platform == "linux":
        return ru_maxrss / 1024
    raise RuntimeError("peak RSS conversion supports macOS and Linux only")


def run_with_rss(command: list[str], timeout: float,
                 expected: int) -> tuple[float, float]:
    """Reap this process with wait4 to obtain its individual peak RSS."""
    with tempfile.TemporaryFile(mode="w+t") as errors:
        start = time.perf_counter()
        child = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                 stderr=errors)
        deadline = start + timeout
        try:
            while True:
                pid, status, usage = os.wait4(child.pid, os.WNOHANG)
                if pid:
                    child.returncode = os.waitstatus_to_exitcode(status)
                    break
                if time.perf_counter() >= deadline:
                    raise subprocess.TimeoutExpired(command, timeout)
                time.sleep(0.01)
        except BaseException:
            if child.returncode is None:
                child.kill()
                _, status, _ = os.wait4(child.pid, 0)
                child.returncode = os.waitstatus_to_exitcode(status)
            raise
        elapsed_ms = (time.perf_counter() - start) * 1000
        if child.returncode != expected:
            errors.seek(0)
            details = errors.read(4096).strip()
            raise RuntimeError(f"QEMU returned {child.returncode}, "
                               f"expected {expected}: {details}")
        return elapsed_ms, peak_rss_mib(usage.ru_maxrss)


def with_smp(command: list[str], cpus: int, maxcpus: int,
             guest_mib: int) -> list[str]:
    """Reuse existing QEMU benchmark arguments; only replace SMP and RAM."""
    args = command.copy()
    for flag, value in (("-smp", f"cpus={cpus},maxcpus={maxcpus}"),
                        ("-m", f"{guest_mib}M")):
        index = args.index(flag)
        args[index + 1] = value
    return args


def self_test() -> None:
    command = with_smp(["qemu", "-smp", "1", "-m", "16M"], 2, 8, 256)
    assert command == ["qemu", "-smp", "cpus=2,maxcpus=8", "-m", "256M"]
    elapsed, rss = run_with_rss([sys.executable, "-c",
        "import sys; mem = bytearray(4 * 1024 * 1024); "
        "mem[0] = 1; sys.exit(33)"], 10, 33)
    assert elapsed > 0 and rss > 0
    print("SMP peak-RSS subprocess and CLI smoke checks passed")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", default="qemu-system-i386")
    parser.add_argument("--cpus", default="1,2,4,8",
                        help="comma-separated active vCPU counts (default 1,2,4,8)")
    parser.add_argument("--maxcpus", type=int,
                        help="fixed CPU hotplug capacity; default equals active count")
    parser.add_argument("--guest-mib", type=int, default=256)
    parser.add_argument("--tb-size", type=int, metavar="MIB",
                        help="explicit TCG cache MiB; default automatic")
    parser.add_argument("--tcg-thread", choices=("single", "multi"),
                        default="multi")
    parser.add_argument("--split-wx", choices=("auto", "on", "off"),
                        default="auto")
    parser.add_argument("--workload",
                        choices=("startup", "memory", "dispatch",
                                 "branch", "fcomi", "flags"),
                        default="memory")
    parser.add_argument("--loops", type=int, default=200000)
    parser.add_argument("--rounds", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if not hasattr(os, "wait4") or sys.platform not in ("darwin", "linux"):
        parser.error("this benchmark requires macOS or Linux wait4(2)")
    if args.self_test:
        self_test()
        return 0
    try:
        counts = [int(item.strip()) for item in args.cpus.split(",")]
    except ValueError:
        parser.error("--cpus must be a comma-separated sequence of integers")
    if not counts or any(c < 1 for c in counts) or len(set(counts)) != len(counts):
        parser.error("--cpus must contain distinct positive integers")
    if args.maxcpus is not None and args.maxcpus < max(counts):
        parser.error("--maxcpus must be at least the largest active CPU count")
    if args.guest_mib < 1 or args.rounds < 1 or args.timeout <= 0:
        parser.error("guest memory, rounds, and timeout must be positive")
    if args.tb_size is not None and args.tb_size < 1:
        parser.error("--tb-size must be at least 1 MiB")
    if not 1 <= args.loops <= 0xffffffff:
        parser.error("--loops must fit into an unsigned 32-bit count")

    # Do not duplicate the existing deterministic BIOS or QEMU command logic.
    bench = runpy.run_path(str(Path(__file__).with_name("bench-i386-tcg.py")))
    qemu = bench["resolve_qemu"](args.qemu)
    with tempfile.TemporaryDirectory(prefix="qemu-smp-rss-") as directory:
        bios = Path(directory) / "workload.bin"
        bios.write_bytes(bench["make_bios"](args.workload, args.loops))
        print(f"QEMU={qemu} guest={args.guest_mib}MiB workload={args.workload} "
              f"thread={args.tcg_thread} tb={args.tb_size or 'auto'}")
        print("active  maxcpus  median_peak_RSS_MiB  median_wall_ms  RSS_samples_MiB")
        for cpus in counts:
            capacity = args.maxcpus if args.maxcpus is not None else cpus
            command = bench["qemu_command"](qemu, bios, args.tcg_thread,
                                            args.split_wx, args.tb_size)
            command = with_smp(command, cpus, capacity, args.guest_mib)
            values = [run_with_rss(command, args.timeout,
                                   bench["DEBUG_EXIT_STATUS"])
                      for _ in range(args.rounds)]
            elapsed, rss = zip(*values)
            samples = ",".join(f"{sample:.1f}" for sample in rss)
            print(f"{cpus:>6}  {capacity:>7}  {statistics.median(rss):>19.1f}  "
                  f"{statistics.median(elapsed):>14.1f}  [{samples}]")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
