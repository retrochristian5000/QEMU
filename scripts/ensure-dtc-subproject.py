#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Align an existing DTC Git checkout with QEMU's immutable Meson wrap.

This runs before Meson setup, with Git as the source updater.  It does not
run Meson's subproject updater, reset Git, or alter the build directory.
"""

import argparse
import configparser
import hashlib
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
import tempfile


OLD_DTC_URLS = {
    "https://gitlab.com/qemu-project/dtc.git",
    "https://github.com/qemu/dtc.git",
}


class DTCError(Exception):
    pass


def git_command():
    # WHP host-tools.sh may promote a managed Git and export its exact command.
    # Match the submodule updater's GIT selection instead of rediscovering PATH.
    command = os.environ.get("GIT") or "git"
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise DTCError(f"invalid GIT command: {exc}") from exc
    if not argv:
        raise DTCError("GIT must name a Git executable")
    return argv


def git(checkout, *args):
    result = subprocess.run(
        [*git_command(), "-C", str(checkout), *args],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if result.returncode:
        raise DTCError(
            f"git {' '.join(args)} failed: {result.stderr.strip()}"
        )
    return result.stdout.strip()


def refresh_wrap_cache(cache_file, wrap_hash):
    # This is Meson's own SHA-256 text-file marker.  Write it only after
    # verifying the Git revision, and replace it atomically.
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=cache_file.parent,
            prefix=".meson-wrap-", delete=False,
        ) as handle:
            temporary = Path(handle.name)
            handle.write(wrap_hash + "\n")
        os.replace(temporary, cache_file)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def validate_meson_dtc(checkout):
    """Detect the old dtc:tests mismatch before Meson configures its graph."""
    options = checkout / "meson_options.txt"
    if not (checkout / "meson.build").is_file() or not (checkout / "libfdt" / "meson.build").is_file():
        raise DTCError("pinned DTC checkout lacks its Meson libfdt project")
    if not options.is_file() or not re.search(
        r"""(?m)^\s*option\s*\(\s*['"]tests['"]\s*,""",
        options.read_text(encoding="utf-8") if options.is_file() else "",
    ):
        raise DTCError("pinned DTC checkout does not declare the Meson 'tests' option")


def fetch_missing_dtc(source, checkout, url, revision, wrap_hash):
    """Fetch Git to a staging directory; publish only a verified checkout."""
    with tempfile.TemporaryDirectory(prefix=".dtc-fetch-", dir=checkout.parent) as staging:
        pending = Path(staging) / "dtc"
        result = subprocess.run(
            [*git_command(), "init", "-q", str(pending)],
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if result.returncode:
            raise DTCError("git init for DTC failed: " + result.stderr.strip())
        git(pending, "remote", "add", "origin", url)
        git(pending, "fetch", "--depth=1", "--no-tags", "origin", revision)
        git(pending, "checkout", "--detach", revision, "--")
        if git(pending, "rev-parse", "HEAD") != revision:
            raise DTCError("fresh DTC download did not resolve the pinned revision")
        validate_meson_dtc(pending)
        refresh_wrap_cache(pending / ".meson-subproject-wrap-hash.txt", wrap_hash)
        if checkout.exists() or checkout.is_symlink():
            raise DTCError("DTC checkout appeared during fetch; refusing to overwrite it")
        pending.rename(checkout)
    return True


def ensure_dtc(source, no_download=False, fetch_missing=False):
    wrap_file = source / "subprojects" / "dtc.wrap"
    checkout = source / "subprojects" / "dtc"
    config = configparser.ConfigParser(interpolation=None)
    if not config.read(wrap_file, encoding="utf-8") or not config.has_section("wrap-git"):
        raise DTCError(f"missing [wrap-git] specification: {wrap_file}")
    revision = config.get("wrap-git", "revision", fallback="").strip()
    url = config.get("wrap-git", "url", fallback="").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision) or not url:
        raise DTCError("DTC wrap must specify an immutable 40-digit revision and URL")

    wrap_hash = hashlib.sha256(wrap_file.read_bytes()).hexdigest()
    # Normal first use remains a Meson wrap download.  Opt-in Git prefetch
    # repairs hosts where the wrap checkout cannot be materialized safely.
    if not checkout.exists():
        if checkout.is_symlink():
            raise DTCError("DTC checkout is a dangling symlink")
        if not fetch_missing:
            return False
        if no_download:
            raise DTCError("DTC download requested but downloads are disabled")
        if not (source / ".git").exists():
            return False  # Do not mutate release archives.
        return fetch_missing_dtc(source, checkout, url, revision, wrap_hash)
    if not (source / ".git").exists():
        # Release archives may include a pre-extracted (non-Git) DTC source.
        # Such vendored source is not ours to mutate during configure.
        return False
    if checkout.is_symlink() or not checkout.is_dir() or not (checkout / ".git").exists():
        raise DTCError(f"existing DTC source is not a standalone Git checkout: {checkout}")
    if Path(git(checkout, "rev-parse", "--show-toplevel")).resolve() != checkout.resolve():
        raise DTCError("DTC checkout belongs to another Git working tree")

    current = git(checkout, "rev-parse", "HEAD")
    cache_file = checkout / ".meson-subproject-wrap-hash.txt"
    cached_hash = cache_file.read_text(encoding="utf-8").strip() if cache_file.exists() else None
    if current == revision and cached_hash in (None, wrap_hash):
        validate_meson_dtc(checkout)
        return False

    # A stale wrap marker is not a reason to detach a development branch.
    # If the source is already pinned and clean, repair just Meson's marker:
    # no Git fetch, branch switch, or modification of the build directory.
    status = git(checkout, "status", "--porcelain", "--untracked-files=all")
    dirty = "\n".join(line for line in status.splitlines()
                      if line[3:] != ".meson-subproject-wrap-hash.txt")
    if dirty:
        raise DTCError("DTC has local changes; preserving them rather than updating: " + dirty)
    if current == revision:
        validate_meson_dtc(checkout)
        refresh_wrap_cache(cache_file, wrap_hash)
        return True

    # Only an out-of-date source revision needs an actual Git transition.
    # Do not let Meson's updater stash/rebase local work or move a branch.
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
    print(f"Synchronizing DTC to pinned Git revision {revision}", flush=True)
    try:
        if current != revision:
            git(checkout, "fetch", "--depth=1", "--no-tags", "origin", revision)
            git(checkout, "checkout", "--detach", revision, "--")
        if git(checkout, "rev-parse", "HEAD") != revision:
            raise DTCError("Git did not select QEMU's pinned DTC revision")
        validate_meson_dtc(checkout)
        refresh_wrap_cache(cache_file, wrap_hash)
        if not cache_file.is_file() or cache_file.read_text(encoding="utf-8").strip() != wrap_hash:
            raise DTCError("DTC wrap revision cache did not refresh")
    except (DTCError, OSError):
        if changed_origin and git(checkout, "rev-parse", "HEAD") != revision:
            git(checkout, "remote", "set-url", "origin", origin)
        raise
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--fetch-missing", action="store_true",
                        help="fetch pinned DTC from Git before Meson setup")
    args = parser.parse_args()
    try:
        ensure_dtc(args.source.resolve(), args.no_download, args.fetch_missing)
    except (DTCError, OSError) as exc:
        print(f"DTC subproject: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
