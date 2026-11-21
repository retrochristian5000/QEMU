#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Install the validated managed build Bash as an optional QEMU host utility.

This is a host-side script interpreter, never a shell inside an emulated guest.
It does not bootstrap Bash or copy arbitrary system binaries.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import os
from pathlib import Path
import platform
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BASH_HELPER = ROOT / "scripts" / "ensure-bash.py"
RUNTIME_NAME = "whp-qemu-bash"
RECORD_NAME = ".whp-qemu-bash.sha256"


def bash_support():
    spec = importlib.util.spec_from_file_location("whp_ensure_bash", BASH_HELPER)
    if spec is None or spec.loader is None:
        raise RuntimeError("managed Bash validation helper is unavailable")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def managed_bash(build_dir: Path) -> Path:
    directory = build_dir / "deps" / "bash"
    source = directory / "bin" / "bash"
    marker = directory / ".whp-bash-bootstrap"
    if not marker.is_file() or not source.is_file() or source.is_symlink():
        raise RuntimeError(
            "a managed Bash installation is required under BUILD_DIR/deps/bash; "
            "build with BOOTSTRAP_BASH=1 before requesting INSTALL_RUNTIME_BASH=1"
        )
    fields = {}
    for line in marker.read_text(encoding="utf-8").splitlines():
        key, sep, value = line.partition("=")
        if sep:
            fields[key] = value
    for key in ("BASH_GIT_COMMIT", "HOST_SYSTEM", "HOST_MACHINE",
                "BASH_HOST_TRIPLET", "WHP_MACOS_ARCH"):
        if key not in fields:
            raise RuntimeError(f"managed Bash cache lacks required {key}")
    if fields["HOST_SYSTEM"] != platform.system() or fields["HOST_MACHINE"] != platform.machine():
        raise RuntimeError("managed Bash cache is for a different build machine")
    support = bash_support()
    if not support.bash_usable(source):
        raise RuntimeError(f"managed Bash failed its required syntax probe: {source}")
    if fields["BASH_HOST_TRIPLET"] and not support.bash_matches_host(
        source, fields["BASH_HOST_TRIPLET"]
    ):
        raise RuntimeError("managed Bash MACHTYPE does not match its cache marker")
    if fields["WHP_MACOS_ARCH"] == "arm64e" and not support.mach_o_is_arm64e(source):
        raise RuntimeError("managed Bash is not the requested arm64e Mach-O")
    return source


def install_destination(prefix: Path) -> tuple[Path, Path]:
    if not prefix.is_absolute():
        raise RuntimeError(f"QEMU install prefix must be absolute: {prefix}")
    if prefix.is_symlink():
        raise RuntimeError(f"refusing symlinked QEMU install prefix: {prefix}")
    bin_dir = prefix / "bin"
    if bin_dir.is_symlink() or (bin_dir.exists() and not bin_dir.is_dir()):
        raise RuntimeError(f"unsafe QEMU installation bin directory: {bin_dir}")
    destination = bin_dir / RUNTIME_NAME
    record = bin_dir / RECORD_NAME
    if destination.is_symlink() or record.is_symlink():
        raise RuntimeError("refusing to overwrite a symlinked runtime Bash artifact")
    if destination.exists():
        if not destination.is_file() or not record.is_file():
            raise RuntimeError(f"refusing to overwrite an unmanaged Bash: {destination}")
        old_digest = record.read_text(encoding="ascii").strip()
        if old_digest != sha256_file(destination):
            raise RuntimeError(f"installed Bash has changed outside WHP: {destination}")
    elif record.exists() and not record.is_file():
        raise RuntimeError(f"invalid runtime Bash ownership record: {record}")
    return destination, record


def publish(source: Path, destination: Path, record: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    source_digest = sha256_file(source)
    if destination.exists() and sha256_file(destination) == source_digest:
        return

    pending_binary = None
    pending_record = None
    try:
        fd, binary_path = tempfile.mkstemp(
            prefix=".whp-qemu-bash.", dir=destination.parent
        )
        pending_binary = Path(binary_path)
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            shutil.copyfileobj(input_file, output)
        pending_binary.chmod(0o755)
        if not bash_support().bash_usable(pending_binary):
            raise RuntimeError("staged runtime Bash failed the execution probe")

        fd, record_path = tempfile.mkstemp(
            prefix=".whp-qemu-bash-record.", dir=destination.parent
        )
        pending_record = Path(record_path)
        with os.fdopen(fd, "w", encoding="ascii") as output:
            output.write(source_digest + "\n")
        pending_record.chmod(0o644)

        # Do not mutate unrelated QEMU install outputs; only this owned name
        # and its digest record are published after the staged Bash is tested.
        os.replace(pending_binary, destination)
        pending_binary = None
        os.replace(pending_record, record)
        pending_record = None
    finally:
        for pending in (pending_binary, pending_record):
            if pending is not None:
                pending.unlink(missing_ok=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True, type=Path)
    parser.add_argument("--prefix", required=True, type=Path)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--check", action="store_true")
    action.add_argument("--install", action="store_true")
    args = parser.parse_args(argv)
    try:
        if platform.system() == "Windows":
            raise RuntimeError(
                "runtime Bash packaging on Windows needs its POSIX runtime DLLs; "
                "a standalone bash.exe copy is not supported"
            )
        source = managed_bash(args.build_dir)
        destination, record = install_destination(args.prefix)
        if args.install:
            publish(source, destination, record)
            print(f"WHP runtime Bash: {destination}", file=sys.stderr)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: runtime Bash install: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
