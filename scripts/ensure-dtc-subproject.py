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


class DTCError(Exception):
    pass


# QEMU's internal libfdt integration requires the DTC 1.8.1-era Meson
# contract. Newer revisions are acceptable only if the interface still passes.
MIN_DTC_VERSION = (1, 8, 1)


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
    # Git porcelain output begins with two significant status columns.
    # Strip only line terminators, never leading spaces from the first row.
    return result.stdout.rstrip("\r\n")


def meson_wrap_hash(wrap_file, wrap_text=None):
    """Match Meson's SHA-256 of UTF-8 text (with universal newlines)."""
    if wrap_text is None:
        wrap_text = wrap_file.read_text(encoding="utf-8")
    return hashlib.sha256(wrap_text.encode("utf-8")).hexdigest()


def refresh_wrap_cache(cache_file, wrap_hash, wrap_file):
    # The expected hash must still describe the CURRENT wrap file, not a
    # stale snapshot from before a simultaneous source/pin update.  Refuse
    # to install a mismatched marker.  Keep Meson's atomic update behavior.
    if meson_wrap_hash(wrap_file) != wrap_hash:
        raise DTCError("DTC wrap changed during reconciliation; marker not updated")
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


def validate_meson_dtc(checkout, revision=None):
    """Verify QEMU's DTC Meson contract, optionally in a future Git revision.

    Use "git show" to inspect a proposed revision before checking it out, so
    incompatible DTC upgrades leave HEAD and the old marker untouched.
    """
    def source_text(name):
        if revision is not None:
            try:
                return git(checkout, "show", f"{revision}:{name}")
            except DTCError:
                return None
        path = checkout / name
        return path.read_text(encoding="utf-8") if path.is_file() else None

    project = source_text("meson.build")
    libfdt = source_text("libfdt/meson.build")
    if project is None or libfdt is None:
        raise DTCError("pinned DTC checkout lacks its Meson libfdt project")
    if not re.search(r"\bsubdir\s*\(\s*['\"]libfdt['\"]", project):
        raise DTCError("pinned DTC Meson project no longer enters libfdt")
    if not re.search(r"\blibfdt_dep\b", libfdt):
        raise DTCError("pinned DTC no longer exports QEMU's libfdt_dep")

    # Meson 1.1+ supports meson.options; legacy DTC uses meson_options.txt.
    options = source_text("meson.options")
    if options is None:
        options = source_text("meson_options.txt")
    if options is None:
        raise DTCError("pinned DTC checkout lacks meson.options/meson_options.txt")
    for name in ("tools", "yaml", "python", "tests"):
        if not re.search(r"(?m)^\s*option\s*\(\s*['\"]" + name + r"['\"]\s*,", options):
            raise DTCError(f"pinned DTC checkout does not declare the Meson {name!r} option")

    # Read the *version Meson actually declares*, not an incidental version
    # file that might be present in an unrelated or outdated checkout.
    if re.search(r"""\bversion\s*:\s*files\s*\(\s*['"]VERSION\.txt['"]\s*\)""", project):
        version_text = source_text("VERSION.txt")
        if version_text is None:
            raise DTCError("DTC Meson project references a missing VERSION.txt")
        version = version_text.strip()
    else:
        match = re.search(r"""\bversion\s*:\s*['"]([^'"]+)['"]""", project)
        if match is None:
            raise DTCError("DTC Meson project has no verifiable version (minimum 1.8.1)")
        version = match.group(1).strip()
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise DTCError(f"unrecognized DTC Meson version {version!r}; expected MAJOR.MINOR.PATCH")
    detected = tuple(int(part) for part in version.split("."))
    if detected < MIN_DTC_VERSION:
        required = ".".join(str(part) for part in MIN_DTC_VERSION)
        raise DTCError(f"DTC {version} is older than QEMU's required DTC {required}")


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
        refresh_wrap_cache(pending / ".meson-subproject-wrap-hash.txt",
                           wrap_hash, source / "subprojects" / "dtc.wrap")
        if checkout.exists() or checkout.is_symlink():
            raise DTCError("DTC checkout appeared during fetch; refusing to overwrite it")
        pending.rename(checkout)
    return True


def ensure_dtc(source, no_download=False, fetch_missing=False):
    wrap_file = source / "subprojects" / "dtc.wrap"
    checkout = source / "subprojects" / "dtc"
    # Parse and hash the same UTF-8 text snapshot.  Reading the file again
    # after parsing could mix an older revision with a newer checksum when a
    # source updater changes dtc.wrap concurrently.
    wrap_text = wrap_file.read_text(encoding="utf-8")
    config = configparser.ConfigParser(interpolation=None)
    try:
        config.read_string(wrap_text, source=str(wrap_file))
    except configparser.Error as exc:
        raise DTCError(f"invalid DTC wrap {wrap_file}: {exc}") from exc
    if not config.has_section("wrap-git"):
        raise DTCError(f"missing [wrap-git] specification: {wrap_file}")
    revision = config.get("wrap-git", "revision", fallback="").strip()
    url = config.get("wrap-git", "url", fallback="").strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision) or not url:
        raise DTCError("DTC wrap must specify an immutable 40-digit revision and URL")

    wrap_hash = meson_wrap_hash(wrap_file, wrap_text)
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
    # A matching wrap checksum and HEAD are not evidence that DTC's tracked
    # source files are unchanged.  Check Git's actual nonignored worktree
    # state even on the no-op path; ignored build outputs remain untouched.
    if current == revision:
        # Report an incompatible DTC project precisely before checking its
        # separate worktree-integrity condition. Both checks remain enforced.
        validate_meson_dtc(checkout)
    status = git(checkout, "status", "--porcelain", "--untracked-files=all")
    dirty = "\n".join(line for line in status.splitlines()
                      if line[3:] != ".meson-subproject-wrap-hash.txt")
    if dirty:
        raise DTCError("DTC has local changes; preserving them rather than updating: " + dirty)
    if current == revision and cached_hash == wrap_hash:
        return False

    # A stale wrap marker is not a reason to detach a development branch.
    # If the source is already pinned and clean, repair just Meson's marker:
    # no Git fetch, branch switch, or modification of the build directory.
    if current == revision:
        validate_meson_dtc(checkout)
        refresh_wrap_cache(cache_file, wrap_hash, wrap_file)
        return True

    # Only an out-of-date source revision needs an actual Git transition.
    # Do not let Meson's updater stash/rebase local work or move a branch.
    branch = git(checkout, "rev-parse", "--abbrev-ref", "HEAD")
    if branch != "HEAD":
        raise DTCError(f"DTC is on branch {branch!r}; refusing to switch a development branch")
    # A Git source updater does not touch Meson-owned wrap checkouts.  The
    # requested commit may nonetheless already be in DTC's own object store
    # (e.g. after an interrupted previous reconciliation).  Reuse it before
    # attempting network access; --no-download forbids fetch, not a safe local
    # detached checkout.  Never reset/stash or move a development branch.
    pin_is_local = False
    try:
        git(checkout, "cat-file", "-e", revision + "^{commit}")
        pin_is_local = True
    except DTCError:
        pass

    if no_download and not pin_is_local:
        raise DTCError("DTC revision is stale, the pinned commit is not available locally, and downloads are disabled")

    print(f"Synchronizing DTC to pinned Git revision {revision}", flush=True)
    if not pin_is_local:
        # Fetch by the immutable URL from dtc.wrap, never by the checkout's
        # potentially stale or developer-specific "origin".  This preserves
        # configured remotes and avoids rejecting otherwise safe detached trees.
        git(checkout, "fetch", "--depth=1", "--no-tags", url, revision)
    # Reject incompatible *future* revisions before touching the working
    # checkout, Meson marker, or incremental build directory.
    validate_meson_dtc(checkout, revision=revision)
    git(checkout, "checkout", "--detach", revision, "--")
    if git(checkout, "rev-parse", "HEAD") != revision:
        raise DTCError("Git did not select QEMU's pinned DTC revision")
    validate_meson_dtc(checkout)
    refresh_wrap_cache(cache_file, wrap_hash, wrap_file)
    if not cache_file.is_file() or cache_file.read_text(encoding="utf-8").strip() != wrap_hash:
        raise DTCError("DTC wrap revision cache did not refresh")
    return True


def diagnose_dtc(source, stream=None):
    """Report pre-Meson Git state without fetching or modifying the checkout."""
    out = stream if stream is not None else sys.stderr
    wrap = source / "subprojects" / "dtc.wrap"
    checkout = source / "subprojects" / "dtc"
    print("DTC diagnosis: phase=pre-Meson (after Sphinx/PIE, before meson setup)", file=out)
    print("  SHA256 input: UTF-8 dtc.wrap text (universal newlines), not DTC source or environment", file=out)
    for name in ("WHP_SOURCE_UPDATE", "WHP_SOURCE_UPDATE_DONE", "CI",
                 "WHP_SHELL_PROBE_ONLY", "WHP_BUILD_DIR_PROBE_ONLY",
                 "WHP_PORTABLE_PROBE_ONLY", "PYTHON", "WHP_MESON_PROVIDER",
                 "MESON_PACKAGE_CACHE_DIR", "PYTHONHASHSEED"):
        value = os.environ.get(name)
        print("  Environment " + name + ": " +
              (repr(value) if value is not None else "(unset)"), file=out)
    ci = os.environ.get("CI", "")
    update = os.environ.get("WHP_SOURCE_UPDATE", "auto")
    if update == "0":
        reason = "disabled (WHP_SOURCE_UPDATE=0)"
    elif os.environ.get("WHP_SOURCE_UPDATE_DONE") == "1":
        reason = "build.sh marked source refresh as already done"
    elif update == "auto" and any(
        os.environ.get(name) == "1"
        for name in ("WHP_SHELL_PROBE_ONLY", "WHP_BUILD_DIR_PROBE_ONLY",
                     "WHP_PORTABLE_PROBE_ONLY")
    ):
        reason = "build.sh probe-only mode skips automatic source refresh"
    elif update == "auto" and ci not in ("", "0", "false", "FALSE", "False", "no", "NO"):
        reason = "skipped in CI mode"
    else:
        reason = "eligible; checkout guards and Python availability still apply"
    print("  Automatic source reconciliation: " + reason, file=out)
    print("  This diagnosis is read-only; it never refreshes the stored marker", file=out)
    try:
        print("  Git command: " + shlex.join(git_command()), file=out)
    except DTCError as exc:
        print("  Git command: invalid (" + str(exc) + ")", file=out)
    revision = None
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read(wrap, encoding="utf-8")
        revision = config.get("wrap-git", "revision", fallback="unknown")
        print("  Wrap revision: " + revision, file=out)
        print("  Minimum DTC version: " +
              ".".join(map(str, MIN_DTC_VERSION)), file=out)
    except (OSError, configparser.Error) as exc:
        print("  Wrap revision: unreadable (" + str(exc) + ")", file=out)
    if checkout.is_symlink():
        print("  Checkout: symlink (requires manual inspection)", file=out)
        return
    if not checkout.exists():
        print("  Checkout: missing (Meson wrap fetches on first use)", file=out)
        return
    if not (checkout / ".git").exists():
        print("  Checkout: existing non-Git directory", file=out)
        return
    print("  Checkout: existing Git repository", file=out)
    try:
        head = git(checkout, "rev-parse", "HEAD")
        print("  HEAD: " + head, file=out)
        if revision:
            print("  Git revision vs wrap: " +
                  ("pinned" if head == revision else "different"), file=out)
    except (DTCError, OSError) as exc:
        print("  HEAD: unavailable (" + str(exc) + ")", file=out)
    for label, argv in (
        ("Branch", ("rev-parse", "--abbrev-ref", "HEAD")),
        ("HEAD tree SHA", ("rev-parse", "HEAD^{tree}")),
    ):
        try:
            print("  " + label + ": " + git(checkout, *argv), file=out)
        except (DTCError, OSError) as exc:
            print("  " + label + ": unavailable (" + str(exc) + ")", file=out)
    if revision and re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        try:
            print("  Pinned tree SHA: " +
                  git(checkout, "rev-parse", "--verify", revision + "^{tree}"),
                  file=out)
        except (DTCError, OSError) as exc:
            print("  Pinned tree SHA: unavailable locally (" + str(exc) + ")", file=out)
    try:
        changes = git(checkout, "status", "--porcelain", "--untracked-files=all")
        changed = [line for line in changes.splitlines()
                   if line[3:] != ".meson-subproject-wrap-hash.txt"]
        print("  Local changes: " + str(len(changed)) +
              " (nonignored, excluding Meson's wrap marker)", file=out)
        for line in changed[:8]:
            print("  Changed source: " + line, file=out)
    except (DTCError, OSError) as exc:
        print("  Local changes: unavailable (" + str(exc) + ")", file=out)
    try:
        version_file = checkout / "VERSION.txt"
        if version_file.is_file():
            print("  DTC VERSION.txt: " + version_file.read_text(encoding="utf-8").strip(),
                  file=out)
        else:
            project_file = checkout / "meson.build"
            if project_file.is_file():
                match = re.search(r"\bversion\s*:\s*['\"]([^'\"]+)['\"]",
                                  project_file.read_text(encoding="utf-8"))
                print("  DTC Meson version: " + (match.group(1) if match else "unknown"),
                      file=out)
        validate_meson_dtc(checkout)
        print("  DTC Meson interface: compatible with QEMU", file=out)
    except (DTCError, OSError, UnicodeError) as exc:
        print("  DTC Meson interface: incompatible or unreadable (" + str(exc) + ")",
              file=out)
    marker = checkout / ".meson-subproject-wrap-hash.txt"
    try:
        expected = meson_wrap_hash(wrap)
        raw = hashlib.sha256(wrap.read_bytes()).hexdigest()
        actual = marker.read_text(encoding="utf-8").strip() if marker.is_file() else None
        print("  Meson wrap marker: " +
              ("current" if actual == expected else "stale" if actual else "missing"),
              file=out)
        print("  Expected wrap SHA256 (Meson text): " + expected, file=out)
        print("  Stored wrap SHA256: " + (actual if actual else "(missing)"), file=out)
        if raw != expected:
            print("  Wrap line endings: text-normalized hash differs from raw-byte hash",
                  file=out)
            print("  Raw-byte wrap SHA256: " + raw, file=out)
    except (OSError, UnicodeError) as exc:
        print("  Meson wrap marker: unreadable (" + str(exc) + ")", file=out)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", required=True, type=Path)
    parser.add_argument("--no-download", action="store_true")
    parser.add_argument("--fetch-missing", action="store_true",
                        help="fetch pinned DTC from Git before Meson setup")
    parser.add_argument("--diagnose", action="store_true",
                        help="inspect the DTC Git/Meson boundary without changing sources")
    args = parser.parse_args()
    source = args.source.resolve()
    if args.diagnose:
        diagnose_dtc(source)
        return 0
    try:
        ensure_dtc(source, args.no_download, args.fetch_missing)
    except (DTCError, OSError) as exc:
        print(f"DTC subproject: {exc}", file=sys.stderr)
        diagnose_dtc(source)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
