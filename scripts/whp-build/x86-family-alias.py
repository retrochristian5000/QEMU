#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Publish a verified POSIX i386 alias for an x86_64 emulator.

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
import tempfile

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

    if dest.is_symlink() and os.readlink(dest) == BACKEND:
        if dest.resolve() != source.resolve():
            raise ValueError(f"existing alias does not resolve to {BACKEND}: {dest}")
        return "already-present"

    replacing = os.path.lexists(dest)
    if replacing:
        # The explicit alias option owns only this directory entry. Never
        # remove a directory or a special file, and never follow a foreign
        # symlink while publishing the replacement.
        if not dest.is_symlink() and not dest.is_file():
            raise ValueError(f"not a replaceable emulator file: {dest}")
        if source.is_symlink() and source.resolve() == dest.resolve():
            raise ValueError(
                f"{BACKEND} depends on {ALIAS}; replacement would create "
                "a symbolic-link cycle"
            )
    if check_only:
        return "replace-ready" if replacing else "ready"

    # Build the new directory entry away from its destination. os.replace()
    # replaces a regular file or symlink atomically after the backend probe,
    # without opening or writing through a foreign symlink.
    try:
        with tempfile.TemporaryDirectory(
            prefix=".whp-x86-family-", dir=directory
        ) as staging:
            pending = Path(staging) / ALIAS
            pending.symlink_to(BACKEND)
            os.replace(pending, dest)
    except OSError as exc:
        raise ValueError(f"could not publish i386 emulator alias: {exc}") from exc
    if not dest.is_symlink() or os.readlink(dest) != BACKEND:
        raise ValueError(f"new alias failed verification: {dest}")
    return "replaced" if replacing else "created"


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
