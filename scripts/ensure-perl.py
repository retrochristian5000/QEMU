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
from collections import deque
import fcntl
import io
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import (
    clean_host_environment, reconcile_submodule, select_native_cc,
    select_native_sdk, select_bootstrap_cflags, select_bootstrap_ldflags,
)

REL = pathlib.Path("toolchains/perl")
SCHEMA = "7"


def perl_trace(message: str) -> None:
    """Opt-in phase logging; machine-readable stdout stays untouched."""
    if os.environ.get("WHP_PERL_VERBOSE", "0") == "1":
        print(f"WHP Perl: {message}", file=sys.stderr)


def run(argv: list[str], *, cwd: pathlib.Path | None = None,
        env: dict[str, str] | None = None, capture: bool = False,
        unattended: bool = False, timeout: int | None = None,
        phase: str = "command", log_path: pathlib.Path | None = None):
    if capture and log_path is not None:
        raise ValueError("Perl subprocess cannot capture stdout and log it simultaneously")
    directory = str(cwd) if cwd is not None else os.getcwd()
    if log_path is not None:
        print(f"WHP Perl {phase}: running; log={log_path}", file=sys.stderr)
    perl_trace(f"{phase} start: cwd={directory}; command={argv!r}"
               + (f"; log={log_path}" if log_path else ""))
    try:
        if log_path is None:
            result = subprocess.run(
                argv, cwd=cwd, env=env, text=True, check=False,
                stdin=subprocess.DEVNULL if unattended else None,
                stdout=subprocess.PIPE if capture else sys.stderr,
                stderr=subprocess.PIPE if capture else sys.stderr,
                timeout=timeout,
            )
        else:
            log_path.parent.mkdir(parents=True, exist_ok=True)
            # Keep the complete output for failed bootstraps without filling
            # CI or local terminals with thousands of successful build lines.
            with log_path.open("w", encoding="utf-8") as output:
                result = subprocess.run(
                    argv, cwd=cwd, env=env, text=True, check=False,
                    stdin=subprocess.DEVNULL if unattended else None,
                    stdout=output, stderr=subprocess.STDOUT,
                    timeout=timeout,
                )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"unattended Perl {phase} exceeded {timeout}s: cwd={directory}; "
            f"command={argv!r}" + (f"; log={log_path}" if log_path else "")
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"native Perl {phase} could not start: cwd={directory}; "
            f"command={argv!r}; error={exc}"
        ) from exc
    if result.returncode:
        message = result.stderr.strip() if capture else ""
        if log_path is not None:
            with log_path.open("r", encoding="utf-8", errors="replace") as output:
                message = "".join(deque(output, maxlen=20)).strip()
        raise RuntimeError(
            f"native Perl {phase} failed (exit {result.returncode}): "
            f"cwd={directory}; command={argv!r}"
            + (f"; log={log_path}" if log_path else "")
            + (f"\nLast output lines:\n{message}" if message else "")
        )
    perl_trace(f"{phase} complete: exit=0")
    return result.stdout if capture else ""


def root_perl() -> str:
    env = clean_host_environment(os.environ)
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


def valid_perl(path: pathlib.Path, failures: list[str] | None = None) -> bool:
    """Check the installed interpreter, core modules, and host OS.

    Reuse checks need only a boolean. Installation checks can pass a list to
    receive the exact failed condition without repeating the Perl subprocess.
    """
    def reject(reason: str) -> bool:
        if failures is not None:
            failures.append(reason)
        return False

    if not path.is_file():
        return reject(f"Perl executable is missing: {path}")
    if not os.access(path, os.X_OK):
        return reject(f"Perl executable is not executable: {path}")

    # Tag Perl-side failures so that a missing core module is distinguishable
    # from an interpreter that could not start or run a program at all.
    program = (
        'eval { require 5.006; 1 } or do { '
        'print STDERR "WHP_PERL_VERSION:$@"; exit 41 }; '
        'eval { require strict; 1 } or do { '
        'print STDERR "WHP_PERL_MODULE:strict:$@"; exit 42 }; '
        'eval { require warnings; 1 } or do { '
        'print STDERR "WHP_PERL_MODULE:warnings:$@"; exit 42 }; '
        'eval { require Config; 1 } or do { '
        'print STDERR "WHP_PERL_MODULE:Config:$@"; exit 42 }; '
        # Autom4te uses more core modules than strict/warnings/Config.
        # Check the modules that its scripts actually import at runtime.
        'for my $module (qw(Carp Class::Struct Cwd Data::Dumper Exporter '
        'Fcntl File::Basename File::Compare File::Copy File::Find '
        'File::Spec File::Temp Getopt::Long IO::File POSIX '
        'Text::ParseWords Time::HiRes)) { '
        'eval "require $module; 1" or do { '
        'print STDERR "WHP_PERL_MODULE:$module:$@"; exit 42 }; '
        '} '
        'my $os = $Config::Config{osname}; '
        'print "whp-perl-native:$os\n";'
    )
    try:
        result = subprocess.run(
            [str(path), "-e", program], text=True, errors="replace",
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=clean_host_environment(os.environ),
            check=False, timeout=15,
        )
    except subprocess.TimeoutExpired:
        return reject(f"Perl interpreter timed out after 15 seconds: {path}")
    except OSError as exc:
        return reject(f"Perl interpreter could not start: {path}: {exc}")

    if result.returncode:
        detail = result.stderr.strip()
        if "WHP_PERL_MODULE:" in detail:
            label = detail.split("WHP_PERL_MODULE:", 1)[1]
            module, _, diagnostic = label.partition(":")
            return reject(
                f"Perl core module {module!r} failed to load (exit "
                f"{result.returncode}): {diagnostic.strip() or 'no details'}; "
                f"interpreter={path}"
            )
        if "WHP_PERL_VERSION:" in detail:
            diagnostic = detail.split("WHP_PERL_VERSION:", 1)[1].strip()
            return reject(
                f"Perl interpreter version check failed (exit "
                f"{result.returncode}): {diagnostic or 'no details'}; "
                f"interpreter={path}"
            )
        return reject(
            f"Perl interpreter exited with status {result.returncode}: "
            f"{detail or 'no stderr output'}; interpreter={path}"
        )

    if not result.stdout.startswith("whp-perl-native:"):
        return reject(
            f"Perl interpreter returned unexpected validation output: "
            f"{result.stdout.strip()!r}; stderr={result.stderr.strip()!r}; "
            f"interpreter={path}"
        )
    configured = result.stdout.strip().split(":", 1)[1]
    if not configured:
        return reject(f"Perl Config.pm returned an empty osname: interpreter={path}")

    expected = {"Darwin": "darwin", "Linux": "linux",
                "FreeBSD": "freebsd", "NetBSD": "netbsd",
                "OpenBSD": "openbsd"}.get(platform.system())
    if expected is not None and configured != expected:
        return reject(
            f"Perl Config.pm OS mismatch: reported={configured!r}, "
            f"expected={expected!r}; interpreter={path}"
        )
    return True


def validate_installed_core_headers(executable: pathlib.Path,
                                    prefix: pathlib.Path, compiler: str,
                                    sdk: str, work: pathlib.Path) -> None:
    """Compile Perl's installed C/XS headers with its native build toolchain.

    A valid interpreter/Config.pm is not evidence that its CORE development
    headers were installed or belong to the same prefix. Do this only after
    the managed Perl installation exists, and on cached reuse: no seed Perl
    headers are required to bootstrap Perl itself.
    """
    # The common cleaner now excludes Perl runtime injection as well.
    env = clean_host_environment(os.environ)
    if sdk:
        env["SDKROOT"] = sdk
    config = run(
        [str(executable), "-MConfig", "-e",
         'print join "\\0", map { defined $Config{$_} ? $Config{$_} : "" } '
         'qw(archlibexp ccflags cppflags);'],
        env=env, capture=True, phase="installed CORE Config",
    )
    fields = config.split("\0")
    if len(fields) != 3 or not fields[0]:
        raise RuntimeError("installed Perl Config lacks archlibexp/ccflags/cppflags")
    archlib, ccflags, cppflags = fields
    core = (pathlib.Path(archlib) / "CORE").resolve()
    # Resolve symlinks, but reject a Config pointing at the seed or a stale
    # Homebrew/system Perl development package outside this managed prefix.
    if not core.is_relative_to(prefix.resolve()):
        raise RuntimeError(
            f"installed Perl CORE headers are outside managed prefix: {core}"
        )
    for header in ("EXTERN.h", "perl.h", "XSUB.h", "config.h", "embed.h"):
        entry = core / header
        if not entry.is_file():
            raise RuntimeError(f"installed Perl CORE header missing: {entry}")
        if not entry.resolve().is_relative_to(prefix.resolve()):
            raise RuntimeError(
                f"installed Perl CORE header escapes managed prefix: {entry}"
            )
    try:
        flags = shlex.split(ccflags) + shlex.split(cppflags)
    except ValueError as exc:
        raise RuntimeError(f"installed Perl Config C flags are malformed: {exc}") from exc

    work.mkdir(parents=True, exist_ok=True)
    # Install only an object: -Uuseshrplib is deliberate and the embed/link
    # contract differs between executables and loadable XS modules.
    with tempfile.TemporaryDirectory(prefix="core-headers-", dir=work) as temp:
        source = pathlib.Path(temp) / "probe.c"
        output = pathlib.Path(temp) / "probe.o"
        source.write_text(
            "#include <EXTERN.h>\n"
            "#include <perl.h>\n"
            "#include <XSUB.h>\n"
            "#ifndef PERL_REVISION\n"
            "#error Perl headers do not define PERL_REVISION\n"
            "#endif\n"
            "int whp_perl_core_header_probe(void) { return PERL_REVISION > 0; }\n",
            encoding="utf-8",
        )
        sysroot = (["-isysroot", sdk]
                   if sdk and platform.system() == "Darwin" else [])
        run([compiler, *sysroot, "-I", str(core), *flags,
             "-c", str(source), "-o", str(output)],
            env=env, phase="installed CORE header compile",
            log_path=work / "header-compile.log")


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
        f"-Dld={compiler}", "-Uuseshrplib", "-Uversiononly",
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
    # Development Perl normally enables version-only installation, leaving
    # no bin/perl. Our private managed prefix requires the unversioned name.
    # -Uversiononly must remain explicit even when -Dusedevel is selected.
    if minor % 2:
        options.append("-Dusedevel")
    return options



def require_configured_toolchain(source: pathlib.Path,
                                 prefix: pathlib.Path, compiler: str,
                                 ar: str, ranlib: str, cflags: str = "",
                                 ldflags: str = "") -> None:
    """Check effective metaconfig results, not just requested -D options.

    Perl's OS hints and archive/link probes can change configuration after
    it initially accepts command-line options. Parse only the needed shell
    assignments; never source config.sh or eval configuration text.
    """
    try:
        lines = (source / "config.sh").read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise RuntimeError("Perl Configure did not generate config.sh") from exc
    required = ("prefix", "installbin", "versiononly", "cc", "ld", "ar",
                "full_ar", "ranlib", "ccflags", "ldflags", "osname")
    values: dict[str, str] = {}
    for line in lines:
        match = re.fullmatch(r"([a-z][a-z0-9_]*)=(.*)", line)
        if not match or match.group(1) not in required:
            continue
        key, raw = match.groups()
        if key in values:
            raise RuntimeError(f"Perl config.sh has duplicate {key!r}")
        try:
            parsed = shlex.split(raw, posix=True)
        except ValueError as exc:
            raise RuntimeError(f"Perl config.sh has malformed {key!r}") from exc
        if len(parsed) != 1:
            raise RuntimeError(f"Perl config.sh has ambiguous {key!r}")
        values[key] = parsed[0]
    absent = sorted(set(required) - values.keys())
    if absent:
        raise RuntimeError(f"Perl config.sh lacks {', '.join(absent)}")
    wanted = {"prefix": str(prefix), "installbin": str(prefix / "bin"),
              "cc": compiler, "ld": compiler,
              "ar": ar, "full_ar": ar}
    for key, expected in wanted.items():
        if values[key] != expected:
            raise RuntimeError(
                f"Perl Configure replaced {key}: expected {expected!r}, "
                f"got {values[key]!r}"
            )
    if values["versiononly"] != "undef":
        raise RuntimeError(
            "Perl Configure enabled version-only installation: "
            f"versiononly={values['versiononly']!r}; "
            "managed Perl requires an unversioned bin/perl"
        )
    # metaconfig may legitimately replace ranlib with an indexing operation
    # performed by the same admitted ar; foreign tools are never accepted.
    admitted_indexers = {ranlib, f"{ar} s", f"{ar} ts"}
    if values["ranlib"] not in admitted_indexers:
        raise RuntimeError(
            f"Perl Configure selected an unexpected archive indexer: "
            f"{values['ranlib']!r} (expected {ranlib!r} or selected ar)"
        )
    expected_os = {"Darwin": "darwin", "Linux": "linux",
                   "FreeBSD": "freebsd", "NetBSD": "netbsd",
                   "OpenBSD": "openbsd"}.get(platform.system())
    if expected_os is not None and values["osname"] != expected_os:
        raise RuntimeError(
            f"Perl Configure detected wrong host OS: {values['osname']!r}; "
            f"expected {expected_os!r}"
        )
    for key, requested in (("ccflags", cflags), ("ldflags", ldflags)):
        try:
            expected_tokens = shlex.split(requested)
            actual_tokens = shlex.split(values[key])
        except ValueError as exc:
            raise RuntimeError(f"Perl Configure returned invalid {key}") from exc
        missing = [flag for flag in expected_tokens if flag not in actual_tokens]
        if missing:
            raise RuntimeError(
                f"Perl Configure dropped selected {key}: {missing!r}"
            )


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


def select_native_archive_pair() -> tuple[str, str]:
    """Validate one build-machine ar and its matching ranlib for Perl.

    QEMU's artifact AR is deliberately not a root-tool override. The seed
    accepts WHP_AR_SEED/AR_FOR_BUILD; the indexer then receives the chosen
    executable as a locked WHP_AR_SEED rather than searching for another ar.
    """
    ar_result = subprocess.run(
        ["/bin/sh", str(ROOT / "seeds" / "ar.sh"), "--print-seed"],
        text=True, capture_output=True, check=False,
    )
    if ar_result.returncode or not ar_result.stdout.strip():
        raise RuntimeError("native Perl ar seed unavailable: "
                           + (ar_result.stderr.strip() or "no native archiver"))
    ar_path = ar_result.stdout.strip()

    ranlib_env = os.environ.copy()
    ranlib_env["WHP_AR_SEED"] = ar_path
    ranlib_result = subprocess.run(
        ["/bin/sh", str(ROOT / "seeds" / "ranlib.sh"), "--print-seed"],
        env=ranlib_env, text=True, capture_output=True, check=False,
    )
    if ranlib_result.returncode or not ranlib_result.stdout.strip():
        raise RuntimeError("native Perl ranlib seed unavailable: "
                           + (ranlib_result.stderr.strip() or "no native archive indexer"))
    return ar_path, ranlib_result.stdout.strip()


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

    # Select native ar once, then pin that exact executable for ranlib.
    # The second probe must verify the selected pair, not rediscover a
    # different ar through PATH during Perl's Configure preparation.
    ar_path, ranlib_path = select_native_archive_pair()
    perl_trace(f"native tools: cc={cc}; make={make}; ar={ar_path}; "
               f"ranlib={ranlib_path}; sdk={sdk or '<host-default>'}")
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
                try:
                    validate_installed_core_headers(executable, prefix, cc,
                                                    sdk, work)
                except RuntimeError:
                    restore_previous_install(prefix, backup)
                    raise
                shutil.rmtree(backup)
                return executable
        restore_previous_install(prefix, backup)

    if marker_path.is_file() and marker_path.read_text() == marker:
        if valid_perl(executable):
            validate_installed_core_headers(executable, prefix, cc, sdk, work)
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
            cwd=source, env=env, unattended=True, timeout=900,
            phase="Configure", log_path=work / "configure.log")
        require_configured_toolchain(source, prefix, cc, ar_path,
                                     ranlib_path, cflags, ldflags)
        require_configured_ar(source, ar_path)
        run([make, "perl"], cwd=source, env=env,
            phase="compile", log_path=work / "compile.log")
        built = source / "perl"
        if not built.is_file() or not os.access(built, os.X_OK):
            raise RuntimeError("Perl source build produced no executable")
        run([make, "install"], cwd=source, env=env,
            phase="install", log_path=work / "install.log")
        validation_failures: list[str] = []
        if not valid_perl(executable, validation_failures):
            raise RuntimeError(
                "managed Perl installation validation failed: "
                + "; ".join(validation_failures)
            )
        validate_installed_core_headers(executable, prefix, cc, sdk, work)
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
        if os.environ.get("WHP_PERL_VERBOSE", "0") not in ("0", "1"):
            raise ValueError("WHP_PERL_VERBOSE must be 0 or 1")
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
