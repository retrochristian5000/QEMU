#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Make an explicit, non-destructive POSIX i386 alias for an x86_64 emulator.

This is *system* emulation only. It does not change the compiled QEMU target
architecture or make target-specific QMP, migration, or GDB behavior identical.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import subprocess
import sys

BACKEND = "qemu-system-x86_64"
ALIAS = "qemu-system-i386"


def verify_backend(path: Path) -> None:
    if not path.is_file() or not os.access(path, os.X_OK):
        raise ValueError(f"missing executable {BACKEND}: {path}")
    try:
        result = subprocess.run(
            [str(path.resolve()), "-cpu", "help"],
            capture_output=True, text=True, check=False, timeout=20,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(f"cannot probe {BACKEND}: {exc}") from exc
    if result.returncode != 0:
        raise ValueError(f"{BACKEND} failed the CPU-model probe: {result.stderr.strip()}")
    if not re.search(r"(?<![\w-])qemu32(?![\w-])", result.stdout):
        raise ValueError(f"{BACKEND} does not advertise the qemu32 CPU model")


def ensure_alias(directory: Path, check_only: bool = False) -> str:
    if os.name == "nt":
        raise ValueError("POSIX symbolic links are required; Windows is not supported")
    if not directory.is_dir():
        raise ValueError(f"emulator directory does not exist: {directory}")

    source = directory / BACKEND
    dest = directory / ALIAS
    verify_backend(source)

    if dest.is_symlink():
        if os.readlink(dest) != BACKEND:
            raise ValueError(f"refusing to replace a foreign symbolic link: {dest}")
        if dest.resolve() != source.resolve():
            raise ValueError(f"existing alias does not resolve to {BACKEND}: {dest}")
        return "already-present"
    if os.path.lexists(dest):
        raise ValueError(
            f"refusing to replace an existing i386 executable: {dest}; "
            "preserve or relocate the existing artifact explicitly"
        )
    if check_only:
        return "ready"
    dest.symlink_to(BACKEND)
    if not dest.is_file() or dest.resolve() != source.resolve():
        raise ValueError(f"new alias failed verification: {dest}")
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, required=True,
                        help="directory containing a built or installed qemu-system-x86_64")
    parser.add_argument("--check-only", action="store_true",
                        help="check prerequisites without creating an alias")
    args = parser.parse_args(argv)
    try:
        status = ensure_alias(args.directory, args.check_only)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"WHP x86 family alias: {status}: {args.directory / ALIAS} -> {BACKEND}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
