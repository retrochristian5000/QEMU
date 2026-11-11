#!/usr/bin/env python3
"""Regression contract for Darwin host physical-memory discovery."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OSLIB = ROOT / "util/oslib-posix.c"

text = OSLIB.read_text(encoding="utf-8")

required = [
    '#ifdef CONFIG_DARWIN',
    '#include <sys/sysctl.h>',
    'sysctlbyname("hw.memsize"',
    'uint64_t memsize',
    'memsize > SIZE_MAX',
]

missing = [needle for needle in required if needle not in text]
if missing:
    raise SystemExit(
        "Darwin host-memory discovery is incomplete; missing: "
        + ", ".join(missing)
    )
