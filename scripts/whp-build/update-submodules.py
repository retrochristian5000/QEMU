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


def classify_checkout(target, pin, current):
    """Prove ancestry before classifying; shallow gaps are not divergence."""
    if is_ancestor(target, pin, current):
        return "ahead"
    if is_ancestor(target, current, pin):
        return "behind"
    if git(target, "rev-parse", "--is-shallow-repository").stdout.strip() != "true":
        return "divergent"

    # Pin X and newer tip Y can both exist in a depth-one checkout without
    # their intermediate ancestry. Fetch only Git history, never files or HEAD.
    for deepen in (64, 256, 1024):
        fetched = git(
            target, "fetch", f"--deepen={deepen}", "--no-tags",
            "--no-recurse-submodules", "origin", check=False,
        )
        if fetched.returncode:
            raise UpdateError(
                f"cannot deepen shallow submodule history in {target}: "
                f"{fetched.stderr.strip() or f'Git exited {fetched.returncode}'}"
            )
        if is_ancestor(target, pin, current):
            return "ahead"
        if is_ancestor(target, current, pin):
            return "behind"
    return "incomplete"


def indexed_gitlink(source, path, pin):
    """Never let an unrelated staged gitlink redirect a checkout."""
    indexed = git(source, "ls-files", "--stage", "--", path).stdout.strip()
    return indexed == f"160000 {pin} 0\t{path}"


def remote_refresh(source, path):
    """Explicit, single-submodule remote update; normal builds stay pinned."""
    links = dict(pinned_gitlinks(source))
    if path not in links:
        raise UpdateError(f"{path}: not a recorded QEMU Git submodule")
    pin = links[path]
    if not indexed_gitlink(source, path, pin):
        raise UpdateError(
            f"{path}: staged gitlink differs from QEMU HEAD; "
            "preserve the index before remote refresh"
        )
    records = git(source, "config", "-f", ".gitmodules", "--get-regexp",
                  r"^submodule\..*\.path$", check=False)
    if records.returncode not in (0, 1):
        raise UpdateError(f"{path}: cannot read .gitmodules path declarations")
    names = []
    for line in records.stdout.splitlines():
        key, sep, configured_path = line.partition(" ")
        if sep and configured_path == path:
            names.append(key[len("submodule."):-len(".path")])
    if len(names) != 1:
        raise UpdateError(f"{path}: expected exactly one .gitmodules declaration")
    key = f"submodule.{names[0]}.branch"
    configured = git(source, "config", "--get", key, check=False)
    if configured.returncode == 1:
        configured = git(source, "config", "-f", ".gitmodules", "--get", key,
                         check=False)
    if configured.returncode != 0 or not configured.stdout.strip():
        raise UpdateError(
            f"{path}: --remote requires a configured submodule branch"
        )
    branch = configured.stdout.strip()
    if (branch == "." or
            git(source, "check-ref-format", "--branch", branch,
                check=False).returncode):
        raise UpdateError(f"{path}: unsupported tracking branch {branch!r}")

    target = source / path
    if target.is_symlink() or not (target / ".git").exists():
        raise UpdateError(
            f"{path}: initialize the non-symlinked pinned submodule "
            "before --remote"
        )
    top = git(target, "rev-parse", "--show-toplevel").stdout.strip()
    if Path(top).resolve() != target.resolve():
        raise UpdateError(f"{path}: unexpected Git worktree")
    current = git(target, "rev-parse", "--verify", "HEAD").stdout.strip()
    attached = git(target, "symbolic-ref", "--quiet", "--short", "HEAD",
                   check=False)
    if attached.returncode not in (0, 1):
        raise UpdateError(f"{path}: cannot inspect current branch")
    if attached.returncode == 0:
        raise UpdateError(
            f"{path}: attached development branch "
            f"{attached.stdout.strip()!r} preserved"
        )
    if git(target, "status", "--porcelain",
           "--untracked-files=all").stdout.strip():
        raise UpdateError(
            f"{path}: local edits preserved; refusing --remote checkout"
        )

    parent = git(source, "rev-parse", "HEAD").stdout.strip()
    ref = f"refs/heads/{branch}:refs/remotes/origin/{branch}"
    git(target, "fetch", "--no-tags", "--no-recurse-submodules", "origin", ref)
    tip_ref = f"refs/remotes/origin/{branch}^{{commit}}"
    tip = git(target, "rev-parse", "--verify", tip_ref).stdout.strip()
    # Shallow histories can conceal genuine descendant relationships.
    # Deepen only on an ambiguous result, without moving either checkout.
    shallow = git(target, "rev-parse",
                  "--is-shallow-repository").stdout.strip() == "true"
    if shallow and (
        not is_ancestor(target, pin, tip) or
        not (is_ancestor(target, current, tip) or
             is_ancestor(target, tip, current))
    ):
        for depth in (64, 256, 1024):
            git(target, "fetch", f"--deepen={depth}", "--no-tags",
                "--no-recurse-submodules", "origin", ref)
            if is_ancestor(target, pin, tip) and (
                is_ancestor(target, current, tip) or
                is_ancestor(target, tip, current)
            ):
                break

    if not is_ancestor(target, pin, tip):
        raise UpdateError(
            f"{path}: remote {branch} does not provably descend "
            "from recorded gitlink"
        )
    if current == tip:
        print(f"WHP submodules: {path}: remote {branch} "
              f"already at {tip[:12]}", file=sys.stderr)
        return
    if is_ancestor(target, tip, current):
        print(f"WHP submodules: {path}: preserving newer local "
              f"{current[:12]} ahead of remote {tip[:12]}",
              file=sys.stderr)
        return
    if not is_ancestor(target, current, tip):
        raise UpdateError(
            f"{path}: local history diverges from remote {branch}; "
            "refusing checkout"
        )
    if (
        git(source, "rev-parse", "HEAD").stdout.strip() != parent or
        not indexed_gitlink(source, path, pin) or
        git(target, "rev-parse", "HEAD").stdout.strip() != current or
        git(target, "status", "--porcelain",
            "--untracked-files=all").stdout.strip() or
        git(target, "rev-parse", "--verify", tip_ref).stdout.strip() != tip
    ):
        raise UpdateError(f"{path}: source state changed during remote refresh")
    # --no-fetch ensures that the SHA checked above is the one selected.
    # --checkout overrides developer-configured merge/rebase update modes.
    git(source, "submodule", "update", "--remote", "--no-fetch",
        "--checkout", "--", path)
    if git(target, "rev-parse", "HEAD").stdout.strip() != tip:
        raise UpdateError(
            f"{path}: --remote failed to reach verified commit {tip}"
        )
    print(
        f"WHP submodules: {path}: remote {branch} -> {tip[:12]}; "
        "parent gitlink unchanged; review and commit separately",
        file=sys.stderr,
    )


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

        # Recover intervening history before mistaking a shallow descendant
        # for a divergent checkout. An unreachable origin still cannot prove it.
        try:
            relation = classify_checkout(target, pin, current)
        except UpdateError as exc:
            if preserve_if_auto(path, str(exc)):
                protected += 1
                continue
            raise
        if relation == "ahead":
            ahead += 1
            print(
                f"WHP submodules: {path}: local {current[:12]} descends from "
                f"pin {pin[:12]}; preserving newer checkout (gitlink unchanged)",
                file=sys.stderr,
            )
            continue

        # Only a verified fast-forward may change an initialized checkout.
        if relation != "behind":
            reason = ("incomplete shallow history" if relation == "incomplete"
                      else "divergent history")
            if preserve_if_auto(path, reason):
                protected += 1
                continue
            raise UpdateError(
                f"submodule {path} has {reason} "
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
        if not indexed_gitlink(source, path, pin):
            if preserve_if_auto(path, "staged gitlink differs from HEAD"):
                protected += 1
                continue
            raise UpdateError(
                f"submodule {path} has a staged gitlink differing from HEAD; "
                "no checkout was updated"
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
        if not indexed_gitlink(source, path, pin):
            raise UpdateError(f"submodule {path} index changed during refresh")
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
    parser.add_argument("--remote", action="store_true",
                        help="explicitly follow one submodule tracking branch")
    parser.add_argument("paths", nargs="*",
                        help="exactly one submodule path when using --remote")
    args = parser.parse_args()
    try:
        if args.remote:
            if len(args.paths) != 1:
                raise UpdateError("--remote needs exactly one submodule path")
            remote_refresh(args.source.resolve(), args.paths[0])
        else:
            if args.paths:
                raise UpdateError("submodule paths require --remote")
            refresh(args.source.resolve())
    except UpdateError as exc:
        print(f"error: WHP submodule update: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
