#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import argparse
import os
import platform
import subprocess
from typing import Mapping

MACOS_POWER_PROFILES = ("eco", "balanced", "performance")
GIB = 1024 ** 3
# Scheduling estimate, not a hard limit on a compiler's resident memory.
MACOS_JOB_MEMORY = 3 * GIB // 2


def macos_usable_memory() -> int:
    """Prefer usable physical memory, falling back to installed capacity."""
    for key in ("hw.memsize_usable", "hw.memsize"):
        try:
            result = subprocess.run(
                ["/usr/sbin/sysctl", "-n", key],
                capture_output=True, text=True, check=True, timeout=2,
            )
            size = int(result.stdout.strip(), 10)
        except (OSError, subprocess.SubprocessError, ValueError):
            continue
        if size > 0:
            return size
    return 0


def macos_memory_job_limit(memory_bytes: int) -> int:
    """Budget at most half the usable RAM for concurrent build jobs."""
    if memory_bytes <= 0:
        return 2
    return max(1, (memory_bytes // 2) // MACOS_JOB_MEMORY)


def _positive_int(name: str, value: str) -> int:
    try:
        number = int(value, 10)
    except ValueError as exc:
        raise ValueError(f"{name} must be a positive integer: {value}") from exc
    if number < 1:
        raise ValueError(f"{name} must be a positive integer: {value}")
    return number

def recommended_macos_jobs(profile: str, cpu_count: int) -> int:
    if profile not in MACOS_POWER_PROFILES:
        raise ValueError(
            "MACOS_BUILD_POWER must be one of: "
            + ", ".join(MACOS_POWER_PROFILES)
            + f": {profile}"
        )
    total = max(1, cpu_count)
    if profile == "performance":
        return total
    if profile == "eco":
        return min(2, total)
    if total <= 2:
        return total
    return min(6, max(2, (total + 1) // 2))

def resolve_jobs(
    environ: Mapping[str, str] | None = None,
    *,
    system: str | None = None,
    cpu_count: int | None = None,
    memory_bytes: int | None = None,
) -> int:
    env = os.environ if environ is None else environ
    explicit = env.get("JOBS", "")
    if explicit:
        return _positive_int("JOBS", explicit)
    total = max(1, cpu_count if cpu_count is not None else (os.cpu_count() or 1))
    host_system = system if system is not None else platform.system()
    if host_system != "Darwin":
        return total
    profile = env.get("MACOS_BUILD_POWER", "balanced")
    cpu_jobs = recommended_macos_jobs(profile, total)
    memory = macos_usable_memory() if memory_bytes is None else memory_bytes
    return min(cpu_jobs, macos_memory_job_limit(memory))

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--print-jobs", action="store_true")
    parser.parse_args()
    try:
        jobs = resolve_jobs()
    except ValueError as exc:
        parser.error(str(exc))
    print(jobs)
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
