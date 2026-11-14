#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned Perl fork as a native host interpreter after the seed phase.

Perl's source uses its own Configure and self-hosting miniperl. A validated
external Perl seed remains available to earlier Autotools stages and for
rebuilding managed Perl; neither the source checkout nor host Perl is altered.
"""

from __future__ import annotations

import argparse
from contextlib import contextmanager
import fcntl
import io
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import (
    clean_host_environment, reconcile_submodule, select_native_cc,
    select_native_sdk, select_bootstrap_cflags, select_bootstrap_ldflags,
)

REL = pathlib.Path("toolchains/perl")
SCHEMA = "6"


def run(argv: list[str], *, cwd: pathlib.Path | None = None,
        env: dict[str, str] | None = None, capture: bool = False,
        unattended: bool = False, timeout: int | None = None):
    try:
        result = subprocess.run(
            argv, cwd=cwd, env=env, text=True, check=False,
            stdin=subprocess.DEVNULL if unattended else None,
            stdout=subprocess.PIPE if capture else sys.stderr,
            stderr=subprocess.PIPE if capture else sys.stderr,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"unattended Perl Configure exceeded {timeout}s: {argv!r}"
        ) from exc
    if result.returncode:
        message = result.stderr.strip() if capture else ""
        raise RuntimeError(
            f"native Perl command failed ({result.returncode}): {argv!r}"
            + (f": {message}" if message else "")
        )
    return result.stdout if capture else ""


def root_perl() -> str:
    env = os.environ.copy()
    seed = env.get("WHP_PERL_BOOTSTRAP_SEED", "")
    if seed:
        env["WHP_PERL_SEED"] = seed
        env["PERL"] = seed
    result = subprocess.run(
        ["/bin/sh", str(ROOT / "seeds" / "perl.sh"), "--print-seed"],
        env=env, text=True, capture_output=True, check=False,
    )
    path = result.stdout.strip()
    if result.returncode or not path:
        raise RuntimeError(
            "managed Perl requires an independent working Perl seed: "
            + (result.stderr.strip() or "no seed selected")
        )
    return path


def valid_perl(path: pathlib.Path) -> bool:
    if not path.is_file() or not os.access(path, os.X_OK):
        return False
    program = (
        "use 5.006; use strict; use warnings; use Config; "
        "my $os = $Config{osname}; "
        'print "whp-perl-native:$os\\n";'
    )
    try:
        result = subprocess.run(
            [str(path), "-e", program], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode or not result.stdout.startswith("whp-perl-native:"):
        return False
    configured = result.stdout.strip().split(":", 1)[1]
    expected = {"Darwin": "darwin", "Linux": "linux",
                "FreeBSD": "freebsd", "NetBSD": "netbsd",
                "OpenBSD": "openbsd"}.get(platform.system())
    return bool(configured) and (expected is None or configured == expected)


def stage_source(revision: str, destination: pathlib.Path, *, git: str) -> None:
    env = os.environ.copy()
    for name in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                 "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        env.pop(name, None)
    archive = subprocess.run(
        [git, "-C", str(ROOT / REL), "archive", "--format=tar", revision],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if archive.returncode:
        raise RuntimeError(
            "cannot stage pinned Perl source: "
            + archive.stderr.decode("utf-8", "replace").strip()
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as tar:
        tar.extractall(destination)



def configure_arguments(source: pathlib.Path, prefix: pathlib.Path,
                        compiler: str, cflags: str = "",
                        ldflags: str = "", ranlib: str = "", ar: str = "") -> list[str]:
    """Use Perl's supported noninteractive mode and explicit devel consent.

    Perl Configure -des alone refuses odd-numbered development series:
    its devel confirmation defaults to 'no'. Never feed interactive
    answers on stdin, and never consent without checking patchlevel.h.
    """
    patchlevel = (source / "patchlevel.h").read_text(encoding="utf-8")
    match = re.search(
        r"^#define\s+PERL_VERSION\s+(\d+)\b",
        patchlevel, re.MULTILINE,
    )
    if match is None:
        raise RuntimeError("pinned Perl lacks a recognizable PERL_VERSION")
    minor = int(match.group(1))
    options = [
        "/bin/sh", "./Configure", "-des",
        f"-Dprefix={prefix}", f"-Dcc={compiler}",
        "-Uuseshrplib",
    ]
    # Perl Configure uses ccflags/ldflags (not Autoconf CFLAGS/LDFLAGS).
    # Supply one authoritative value for each instead of relying on
    # environment-variable interpretation that differs across hints files.
    if cflags:
        options.append(f"-Dccflags={cflags}")
    if ldflags:
        options.append(f"-Dldflags={ldflags}")
    if ranlib:
        options.append(f"-Dranlib={ranlib}")
    if ar:
        # Configure probes with ar, but Makefile.SH invokes full_ar.
        # Bind both to the same admitted native archiver explicitly.
        options.append(f"-Dar={ar}")
        options.append(f"-Dfull_ar={ar}")
    if minor % 2:
        options.append("-Dusedevel")
    return options


def require_configured_ar(source: pathlib.Path, expected: str) -> None:
    """Reject a Configure result that makes Perl archive with another tool."""
    try:
        makefile = (source / "Makefile").read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError("Perl Configure did not generate a Makefile") from exc
    # Perl Makefile.SH emits exactly one AR = $full_ar assignment.
    configured = re.findall(r"^AR[ \t]*=[ \t]*(.*)$", makefile, re.MULTILINE)
    if len(configured) != 1 or configured[0].strip() != expected:
        actual = configured[0].strip() if len(configured) == 1 else "<missing or ambiguous>"
        raise RuntimeError(
            f"Perl Makefile ar mismatch: expected {expected!r}, got {actual!r}"
        )


@contextmanager
def bootstrap_lock(build_dir: pathlib.Path):
    """Serialize builds sharing a prefix, including validation and recovery."""
    root = build_dir / "bootstrap"
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".perl-bootstrap.lock").open("a+b") as handle:
        deadline = time.monotonic() + 30
        while True:
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise RuntimeError(
                        "another managed Perl bootstrap holds the build lock"
                    )
                time.sleep(0.1)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def restore_previous_install(prefix: pathlib.Path,
                             backup: pathlib.Path) -> None:
    """Preserve the last working interpreter after an interrupted rebuild."""
    if not backup.exists():
        return
    if prefix.exists():
        shutil.rmtree(prefix)
    backup.rename(prefix)


def select_seed_make() -> str:
    """Resolve the pre-Perl GNU Make root, never an unbuilt managed Make."""
    requested = (
        os.environ.get("MAKE_CMD") or os.environ.get("MAKE") or "make"
    )
    candidate = (shutil.which(requested) if "/" not in requested
                 else requested)
    if not candidate or not os.access(candidate, os.X_OK):
        raise RuntimeError(f"native Perl bootstrap needs GNU Make: {requested}")
    candidate = str(pathlib.Path(candidate).resolve())
    try:
        result = subprocess.run(
            [candidate, "--version"], capture_output=True, text=True,
            check=False, timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(
            f"native Perl GNU Make seed cannot execute: {candidate}"
        ) from exc
    first_line = result.stdout.splitlines()[0] if result.stdout else ""
    if result.returncode or not first_line.startswith("GNU Make "):
        raise RuntimeError(
            f"native Perl requires a working GNU Make seed: {candidate}"
        )
    return candidate


def bootstrap(build_dir: pathlib.Path) -> pathlib.Path:
    seed = root_perl()
    git = os.environ.get("WHP_GIT_SEED") or shutil.which("git")
    if not git:
        raise RuntimeError("native Perl bootstrap requires the selected Git seed")
    # Validate native prerequisites before source reconciliation: a missing
    # archiver or SDK must not trigger unnecessary submodule fetches.
    cc = select_native_cc(ROOT)
    sdk = select_native_sdk(ROOT)
    make = select_seed_make()

    # Select the archive tool before ranlib, which validates this same pair.
    ar_result = subprocess.run(
        ["/bin/sh", str(ROOT / "seeds" / "ar.sh"), "--print-seed"],
        text=True, capture_output=True, check=False,
    )
    if ar_result.returncode or not ar_result.stdout.strip():
        raise RuntimeError("native Perl ar seed unavailable: "
                           + (ar_result.stderr.strip() or "no native archiver"))
    ar_path = ar_result.stdout.strip()

    # Keep archive indexing native to the selected compiler and SDK.
    ranlib = subprocess.run(
        ["/bin/sh", str(ROOT / "seeds" / "ranlib.sh"), "--print-seed"],
        text=True, capture_output=True, check=False,
    )
    if ranlib.returncode or not ranlib.stdout.strip():
        raise RuntimeError("native Perl ranlib seed unavailable: "
                           + (ranlib.stderr.strip() or "no native archive indexer"))
    ranlib_path = ranlib.stdout.strip()
    if os.environ.get("WHP_ARCHIVE_VERBOSE") == "1":
        print(f"WHP Perl archive tools: ar={ar_path}; ranlib={ranlib_path}; cc={cc}",
              file=sys.stderr)

    # All host roots are now known. Reconcile the source only after the
    # native toolchain pair has passed its archive-and-link probes.
    revision = reconcile_submodule(ROOT, REL, git=git)

    cflags = select_bootstrap_cflags("perl", cc)
    ldflags = select_bootstrap_ldflags("perl", cc, cflags=cflags)
    prefix = build_dir / "deps" / "perl"
    executable = prefix / "bin" / "perl"
    marker_path = prefix / ".whp-perl-bootstrap"
    marker = (
        f"SCHEMA={SCHEMA}\nSOURCE_REVISION={revision}\n"
        f"SEED_PERL={seed}\nCC_FOR_BUILD={cc}\n"
        f"MAKE={make}\nAR={ar_path}\nRANLIB={ranlib_path}\nSDKROOT={sdk}\n"
        f"CFLAGS={cflags}\nLDFLAGS={ldflags}\n"
    )
    work = build_dir / "bootstrap" / "perl"
    backup = build_dir / "bootstrap" / "perl-previous-install"

    # A terminated process may have left the old installation parked here.
    # Restore it before examining the fingerprint or clearing the work tree.
    if backup.exists():
        if marker_path.is_file() and marker_path.read_text() == marker:
            if valid_perl(executable):
                shutil.rmtree(backup)
                return executable
        restore_previous_install(prefix, backup)

    if marker_path.is_file() and marker_path.read_text() == marker:
        if valid_perl(executable):
            return executable

    source = work / "source"
    shutil.rmtree(work, ignore_errors=True)
    stage_source(revision, source, git=git)
    for name in ("Configure", "Makefile.SH", "perl.c", "miniperlmain.c"):
        if not (source / name).is_file():
            raise RuntimeError("pinned Perl source lacks required file: " + name)

    env = clean_host_environment(os.environ)
    env["CC"] = cc
    env["CC_FOR_BUILD"] = cc
    env["PERL"] = seed
    env["WHP_PERL_SEED"] = seed
    env["WHP_PERL_BOOTSTRAP_SEED"] = seed
    env["MAKE"] = make
    env["RANLIB"] = ranlib_path
    env["AR"] = ar_path
    if sdk:
        env["SDKROOT"] = sdk
    # Perl Configure consumes explicit ccflags/ldflags, not inherited
    # Autoconf-style environment variables.
    env.pop("CFLAGS", None)
    env.pop("LDFLAGS", None)

    # Perl records absolute install paths in its Config. Build against the
    # final prefix rather than moving a temporary installation afterward.
    # Keep the old prefix for rollback until configure, build, install and
    # installed-module validation all succeed.
    prefix.parent.mkdir(parents=True, exist_ok=True)
    if prefix.exists():
        prefix.rename(backup)
    try:
        run(configure_arguments(source, prefix, cc, cflags, ldflags,
                                ranlib_path, ar_path),
            cwd=source, env=env, unattended=True, timeout=900)
        require_configured_ar(source, ar_path)
        run([make, "perl"], cwd=source, env=env)
        built = source / "perl"
        if not built.is_file() or not os.access(built, os.X_OK):
            raise RuntimeError("Perl source build produced no executable")
        run([make, "install"], cwd=source, env=env)
        if not valid_perl(executable):
            raise RuntimeError(
                "managed Perl failed installed interpreter/module/OS checks"
            )
        # Never mark an incomplete installation as reusable.
        temporary_marker = marker_path.with_name(marker_path.name + ".tmp")
        temporary_marker.write_text(marker, encoding="utf-8")
        temporary_marker.replace(marker_path)
    except BaseException:
        if backup.exists():
            restore_previous_install(prefix, backup)
        else:
            shutil.rmtree(prefix, ignore_errors=True)
        raise
    if backup.exists():
        shutil.rmtree(backup)
    return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()
    try:
        build_dir = pathlib.Path(args.build_dir).expanduser().resolve()
        with bootstrap_lock(build_dir):
            result = bootstrap(build_dir)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: WHP managed Perl bootstrap failed: {exc}",
              file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
