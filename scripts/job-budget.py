#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
from __future__ import annotations
import argparse
import os
import platform
from typing import Mapping

MACOS_POWER_PROFILES = ("eco", "balanced", "performance")

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
    return recommended_macos_jobs(profile, total)

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
