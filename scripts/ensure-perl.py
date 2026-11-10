#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned Perl fork as a native host interpreter after the seed phase.

Perl's source uses its own Configure and self-hosting miniperl. A validated
external Perl seed remains available to earlier Autotools stages and for
rebuilding managed Perl; neither the source checkout nor host Perl is altered.
"""

from __future__ import annotations

import argparse
import io
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import (
    clean_host_environment, reconcile_submodule, select_native_cc,
    select_native_sdk, select_bootstrap_cflags, select_bootstrap_ldflags,
)

REL = pathlib.Path("toolchains/perl")
SCHEMA = "2"


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
                        compiler: str) -> list[str]:
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
    if minor % 2:
        options.append("-Dusedevel")
    return options



def bootstrap(build_dir: pathlib.Path) -> pathlib.Path:
    seed = root_perl()
    git = os.environ.get("WHP_GIT_SEED") or shutil.which("git")
    if not git:
        raise RuntimeError("native Perl bootstrap requires the selected Git seed")
    revision = reconcile_submodule(ROOT, REL, git=git)
    cc = select_native_cc(ROOT)
    sdk = select_native_sdk(ROOT)
    requested_make = (
        os.environ.get("MAKE_CMD") or os.environ.get("MAKE") or "make"
    )
    make = (shutil.which(requested_make) if "/" not in requested_make
            else requested_make)
    if not make or not os.access(make, os.X_OK):
        raise RuntimeError(f"native Perl bootstrap needs Make: {requested_make}")
    make = str(pathlib.Path(make).resolve())

    cflags = select_bootstrap_cflags("perl", cc)
    ldflags = select_bootstrap_ldflags("perl", cc, cflags=cflags)
    prefix = build_dir / "deps" / "perl"
    executable = prefix / "bin" / "perl"
    marker_path = prefix / ".whp-perl-bootstrap"
    marker = (
        f"SCHEMA={SCHEMA}\nSOURCE_REVISION={revision}\n"
        f"SEED_PERL={seed}\nCC_FOR_BUILD={cc}\n"
        f"MAKE={make}\nSDKROOT={sdk}\n"
        f"CFLAGS={cflags}\nLDFLAGS={ldflags}\n"
    )
    if marker_path.is_file() and marker_path.read_text() == marker:
        if valid_perl(executable):
            return executable

    work = build_dir / "bootstrap" / "perl"
    source = work / "source"
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
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
    if sdk:
        env["SDKROOT"] = sdk
    if cflags:
        env["CFLAGS"] = cflags
    if ldflags:
        env["LDFLAGS"] = ldflags
    # Perl's source tree has a generated, non-Autotools Configure. Configure
    # produces Makefile.SH derivatives in the staged source directory, not in
    # the checkout. Use the validated native compiler and a private prefix.
    # Even unexpected prompts cannot consume the user's terminal or stall
    # an automatic incremental build. A blocked Configure fails promptly.
    run(configure_arguments(source, prefix, cc),
        cwd=source, env=env, unattended=True, timeout=900)
    run([make, "perl"], cwd=source, env=env)
    built = source / "perl"
    if not built.is_file() or not os.access(built, os.X_OK):
        raise RuntimeError("Perl source build produced no executable")
    # Install the interpreter with its matching core modules. Copying a lone
    # 'perl' binary would break 'use strict', 'use Config' and later builders.
    run([make, "install"], cwd=source, env=env)
    if not valid_perl(executable):
        raise RuntimeError("managed Perl failed installed interpreter/module/OS checks")
    marker_path.write_text(marker, encoding="utf-8")
    return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()
    try:
        result = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"error: WHP managed Perl bootstrap failed: {exc}",
              file=sys.stderr)
        return 1
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
