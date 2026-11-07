#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reconcile initialized QEMU Git submodules to HEAD's immutable gitlinks.

The parent updater runs before the managed Git bootstrap. This later stage
uses its promoted GIT executable, preserving uninitialized submodules, local
changes, and attached developer branches.
"""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys


class UpdateError(Exception):
    pass


def git_argv():
    selected = shlex.split(os.environ.get("GIT") or "git")
    if not selected:
        raise UpdateError("GIT selects an empty command")
    return selected


def git(directory, *args, check=True):
    argv = [*git_argv(), "-C", str(directory), *args]
    try:
        result = subprocess.run(
            argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            check=False,
        )
    except OSError as exc:
        raise UpdateError(f"cannot execute selected Git {argv[0]!r}: {exc}") from exc
    if check and result.returncode:
        raise UpdateError(
            f"Git {' '.join(args)} failed in {directory}: "
            f"{result.stderr.strip() or f'exit {result.returncode}'}"
        )
    return result


def pinned_gitlinks(source):
    result = git(source, "ls-tree", "-rz", "HEAD")
    for record in result.stdout.split("\0"):
        if not record:
            continue
        metadata, path = record.split("\t", 1)
        mode, kind, revision = metadata.split()
        if mode == "160000" and kind == "commit":
            yield path, revision


def is_ancestor(target, older, newer):
    result = git(target, "merge-base", "--is-ancestor", older, newer,
                 check=False)
    if result.returncode not in (0, 1):
        raise UpdateError(
            f"cannot compare submodule history in {target}: "
            f"{result.stderr.strip() or 'Git merge-base failed'}"
        )
    return result.returncode == 0


def refresh(source):
    mode = os.environ.get("WHP_SOURCE_UPDATE", "auto")
    if mode not in ("auto", "0", "1"):
        raise UpdateError(f"invalid WHP_SOURCE_UPDATE={mode!r}")
    if mode == "0":
        return
    if mode == "auto" and os.environ.get("CI", "").lower() not in (
        "", "0", "false", "no",
    ):
        return

    # Inspect the parent first, and do not initialize unused toolchains.
    parent = git(source, "rev-parse", "--verify", "HEAD").stdout.strip()
    pending = []
    initialized = 0
    ahead = 0
    protected = 0

    def preserve_if_auto(path, reason):
        # A separate, explicitly selected toolchain still enforces its own
        # source requirements. An unrelated developer checkout must not block
        # automatic QEMU bootstrap or be moved to an older commit.
        if mode != "auto":
            return False
        print(
            f"warning: WHP submodules: {path}: preserving protected checkout "
            f"({reason}); the required toolchain will verify its own source",
            file=sys.stderr,
        )
        return True
    for path, pin in pinned_gitlinks(source):
        target = source / path
        if not (target / ".git").exists():
            continue
        if target.is_symlink():
            raise UpdateError(f"refusing symlinked submodule {path}")
        top = git(target, "rev-parse", "--show-toplevel").stdout.strip()
        if Path(top).resolve() != target.resolve():
            raise UpdateError(f"submodule {path} resolves outside its own checkout")
        initialized += 1
        current = git(target, "rev-parse", "--verify", "HEAD").stdout.strip()
        if current == pin:
            continue

        # Obtain missing pin history without touching HEAD, the index, or files.
        # Never ask 'submodule update' to check out a pin before ancestry is
        # known: that would rewind a newer detached local checkout.
        if git(target, "cat-file", "-e", pin + "^{commit}",
               check=False).returncode:
            fetched = git(
                target, "fetch", "--no-tags", "--no-recurse-submodules",
                "origin", pin, check=False,
            )
            if fetched.returncode:
                reason = fetched.stderr.strip() or f"Git exited {fetched.returncode}"
                if preserve_if_auto(path, f"pinned history fetch failed: {reason}"):
                    protected += 1
                    continue
                raise UpdateError(
                    f"submodule {path} cannot fetch pinned commit {pin}: "
                    f"{reason}; no checkout was updated"
                )
            if git(target, "cat-file", "-e", pin + "^{commit}",
                   check=False).returncode:
                if preserve_if_auto(path, "pinned commit absent after fetch"):
                    protected += 1
                    continue
                raise UpdateError(
                    f"submodule {path} cannot locate pinned commit {pin}; "
                    "no checkout was updated"
                )

        if is_ancestor(target, pin, current):
            ahead += 1
            print(
                f"WHP submodules: {path}: local {current[:12]} descends from "
                f"pin {pin[:12]}; preserving newer checkout (gitlink unchanged)",
                file=sys.stderr,
            )
            continue

        # Only a verified fast-forward may change an initialized checkout.
        # Divergent and shallow/unprovable histories must never be rewound.
        if not is_ancestor(target, current, pin):
            if preserve_if_auto(path, "divergent or incomplete history"):
                protected += 1
                continue
            raise UpdateError(
                f"submodule {path} has divergent or incomplete history "
                f"(local {current[:12]}, pin {pin[:12]}); "
                "refusing non-fast-forward checkout"
            )

        # Preflight every behind-the-pin submodule before moving any checkout.
        modified = git(target, "status", "--porcelain",
                       "--untracked-files=all").stdout
        if modified.strip():
            if preserve_if_auto(path, "local changes on older checkout"):
                protected += 1
                continue
            raise UpdateError(
                f"submodule {path} differs from pin {pin[:12]} and has local "
                "changes; no checkout was updated"
            )
        attached = git(target, "symbolic-ref", "--quiet", "--short", "HEAD",
                       check=False)
        if attached.returncode not in (0, 1):
            raise UpdateError(f"cannot inspect submodule branch for {path}")
        if attached.returncode == 0:
            if preserve_if_auto(path, "attached development branch"):
                protected += 1
                continue
            raise UpdateError(
                f"submodule {path} is on development branch "
                f"{attached.stdout.strip()!r}; no checkout was updated"
            )
        pending.append((path, pin, target))

    if not pending:
        if ahead or protected:
            print(
                f"WHP submodules: preserved {ahead} ahead of pins and "
                f"{protected} protected checkout(s) among {initialized} "
                "initialized; uninitialized sources remain lazy",
                file=sys.stderr,
            )
        else:
            print(f"WHP submodules: {initialized} initialized and pinned; "
                  "uninitialized sources remain lazy", file=sys.stderr)
        return

    for path, pin, target in pending:
        if git(source, "rev-parse", "HEAD").stdout.strip() != parent:
            raise UpdateError("parent QEMU HEAD changed during submodule refresh")
        # The pin was fetched and its ancestry verified during preflight.
        # Avoid unexpected network access or a forced checkout.
        git(source, "submodule", "update", "--init", "--no-fetch", "--", path)
        current = git(target, "rev-parse", "--verify", "HEAD").stdout.strip()
        if current != pin:
            raise UpdateError(
                f"submodule {path} did not reach pinned revision {pin}"
            )
        print(f"WHP submodules: {path} -> {pin[:12]}", file=sys.stderr)
    print(f"WHP submodules: refreshed {len(pending)} of {initialized} initialized "
          f"checkouts; preserved {ahead} ahead of pins and "
          f"{protected} protected checkouts; "
          "uninitialized sources remain lazy", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    args = parser.parse_args()
    try:
        refresh(args.source.resolve())
    except UpdateError as exc:
        print(f"error: WHP submodule update: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
