#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Align an existing Meson-owned DTC checkout with QEMU's immutable wrap.

This runs before Meson setup, not as a separate configuration pass.  It does
not replace the build directory, reset Git, or alter a developer's work.
"""

import argparse
import configparser
import hashlib
from pathlib import Path
import re
import subprocess
import sys


OLD_DTC_URLS = {
    "https://gitlab.com/qemu-project/dtc.git",
    "https://github.com/qemu/dtc.git",
}


class DTCError(Exception):
    pass


def git(checkout, *args):
    result = subprocess.run(
        ["git", "-C", str(checkout), *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise DTCError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def ensure_dtc(source, meson, no_download=False):
    wrap_file = source / "subprojects" / "dtc.wrap"
    checkout = source / "subprojects" / "dtc"
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(wrap_file, encoding="utf-8") or not config.has_section("wrap-git"):
        raise DTCError(f"missing [wrap-git] specification: {wrap_file}")
    revision = config.get("wrap-git", "revision", fallback="").strip()
    url = config.get("wrap-git", "url", fallback="").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision) or not url:
        raise DTCError("DTC wrap must specify an immutable 40-digit revision and URL")

    # A missing directory is Meson's normal first-use download case.
    if not checkout.exists():
        return False
    if not (source / ".git").exists():
        # Release archives may include a pre-extracted (non-Git) DTC source.
        # Such vendored source is not ours to mutate during configure.
        return False
    if checkout.is_symlink() or not checkout.is_dir() or not (checkout / ".git").exists():
        raise DTCError(f"existing DTC source is not a standalone Git checkout: {checkout}")
    if Path(git(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout.resolve():
        raise DTCError("DTC checkout belongs to another Git working tree")

    current = git(checkout, "rev-parse", "HEAD")
    wrap_hash = hashlib.sha256(wrap_file.read_text(encoding="utf-8").encode("utf-8")).hexdigest()
    cache_file = checkout / ".meson-subproject-wrap-hash.txt"
    cached_hash = cache_file.read_text(encoding="utf-8").strip() if cache_file.exists() else None
    if current == revision and cached_hash in (None, wrap_hash):
        return False

    # Do not let Meson's update helper stash/rebase local work or move a branch.
    status = git(checkout, "status", "--porcelain", "--untracked-files=all")
    dirty = "\n".join(line for line in status.splitlines()
                      if line[3:] != ".meson-subproject-wrap-hash.txt")
    if dirty:
        raise DTCError("DTC has local changes; preserving them rather than updating: " + dirty)
    branch = git(checkout, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "HEAD":
        raise DTCError(f"DTC is on branch {branch!r}; refusing to switch a development branch")
    if no_download and current != revision:
        raise DTCError("DTC revision is stale but downloads are disabled")

    origin = git(checkout, "remote", "get-url", "origin")
    if origin != url and origin not in OLD_DTC_URLS:
        raise DTCError(f"DTC origin differs from the wrap URL: {origin!r}; refusing to replace it")

    changed_origin = origin != url
    if changed_origin:
        git(checkout, "remote", "set-url", "origin", url)
    print(f"Synchronizing DTC to pinned revision {revision} using Meson", flush=True)
    try:
        command = [str(meson), "subprojects", "update", "--sourcedir", str(source), "dtc"]
        result = subprocess.run(command, check=False)
        if result.returncode:
            raise DTCError(f"Meson DTC subproject update failed (exit {result.returncode})")
        if git(checkout, "rev-parse", "HEAD") != revision:
            raise DTCError("Meson update returned without selecting QEMU's pinned DTC revision")
        if not cache_file.is_file() or cache_file.read_text(encoding="utf-8").strip() != wrap_hash:
            raise DTCError("Meson did not refresh DTC's wrap revision cache")
    except (DTCError, OSError):
        if changed_origin:
            git(checkout, "remote", "set-url", "origin", origin)
        raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--meson", required=True)
    parser.add_argument("--no-download", action="store_true")
    args = parser.parse_args()
    try:
        ensure_dtc(args.source.resolve(), args.meson, args.no_download)
    except (DTCError, OSError) as exc:
        print(f"DTC subproject: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
