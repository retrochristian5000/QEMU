#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned GNU Awk fork as a native host tool after the seed phase.

The existing POSIX awk seed is a root dependency. Do not promote managed Gawk
until its executable is built and passes the host semantic probe.
"""

from __future__ import annotations

import argparse
import io
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import (clean_host_environment, reconcile_submodule,
                           select_native_cc, select_native_sdk,
                           select_bootstrap_cflags, select_bootstrap_ldflags)

REL = pathlib.Path("toolchains/gawk")
SCHEMA = "1"


def command(argv: list[str], *, cwd: pathlib.Path | None = None,
            env: dict[str, str] | None = None, binary: bool = False):
    result = subprocess.run(
        argv, cwd=cwd, env=env,
        stdout=subprocess.PIPE if binary else sys.stderr,
        stderr=subprocess.PIPE if binary else sys.stderr,
        check=False,
    )
    if result.returncode:
        detail = (result.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(
            f"command failed ({result.returncode}): {argv!r}"
            + (f": {detail}" if detail else "")
        )
    return result.stdout if binary else None


def seed_awk() -> str:
    adapter = ROOT / "seeds" / "awk.sh"
    env = os.environ.copy()
    original = env.get("WHP_AWK_BOOTSTRAP_SEED", "")
    if original:
        env["WHP_AWK_SEED"] = original
        env["AWK"] = original
    proc = subprocess.run(
        ["/bin/sh", str(adapter), "--print-seed"],
        env=env, text=True, capture_output=True, check=False,
    )
    value = proc.stdout.strip()
    if proc.returncode or not value:
        raise RuntimeError("Gawk needs a functional host AWK seed: "
                           + (proc.stderr.strip() or "seed unavailable"))
    # Do not allow an already-promoted managed executable to become the
    # bootstrap seed that would have to rebuild itself.
    return value


def validate_awk(path: pathlib.Path) -> bool:
    if not path.is_file() or not os.access(path, os.X_OK):
        return False
    probes = [
        (["-F", "|", "-v", "wanted=beta",
          '$1=="alpha" && $2==wanted {printf "%s:%d:%d\\n",$2,NF,NR}'],
         "alpha|beta\n", "beta:2:1\n"),
        (['{gsub(/[\\/ ]/,"-",$0);print}'], "A/B C\n", "A-B-C\n"),
        (['BEGIN {a["x"]=7; if (a["x"]!=7) exit 3; print "ok"}'],
         "", "ok\n"),
    ]
    for args, source, expected in probes:
        try:
            result = subprocess.run(
                [str(path), *args], input=source, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                check=False, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return False
        if result.returncode or result.stdout != expected:
            return False
    return True


def stage_source(revision: str, destination: pathlib.Path) -> None:
    subprocess_env = os.environ.copy()
    for key in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
                "GIT_OBJECT_DIRECTORY", "GIT_ALTERNATE_OBJECT_DIRECTORIES"):
        subprocess_env.pop(key, None)
    archive = subprocess.run(
        ["git", "-C", str(ROOT / REL), "archive", "--format=tar", revision],
        env=subprocess_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False,
    )
    if archive.returncode:
        raise RuntimeError(
            "cannot stage pinned Gawk source: "
            + archive.stderr.decode("utf-8", "replace").strip()
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(archive.stdout), mode="r:") as bundle:
        bundle.extractall(destination)


def bootstrap(build_dir: pathlib.Path) -> pathlib.Path:
    seed = seed_awk()
    revision = reconcile_submodule(ROOT, REL)
    sdk = select_native_sdk(ROOT)
    cc = select_native_cc(ROOT)
    make = os.environ.get("MAKE_CMD") or os.environ.get("MAKE") or "gmake"
    make_path = shutil.which(make) if "/" not in make else make
    if not make_path or not os.access(make_path, os.X_OK):
        raise RuntimeError(f"GNU Make is unavailable for managed Gawk: {make}")
    version = subprocess.run([make_path, "--version"], text=True,
                             capture_output=True, check=False)
    if version.returncode or not version.stdout.startswith("GNU Make "):
        raise RuntimeError(f"managed Gawk requires GNU Make: {make_path}")
    cflags = select_bootstrap_cflags("gawk", cc)
    ldflags = select_bootstrap_ldflags("gawk", cc, cflags=cflags)
    prefix = build_dir / "deps" / "gawk"
    marker_path = prefix / ".whp-gawk-bootstrap"
    executable = prefix / "bin" / "gawk"
    marker = ("WHP_GAWK_SCHEMA=" + SCHEMA + "\n"
              + "SOURCE_REVISION=" + revision + "\n"
              + "SEED_AWK=" + seed + "\n"
              + "CC_FOR_BUILD=" + cc + "\n"
              + "MAKE=" + str(make_path) + "\n"
              + "SDKROOT=" + sdk + "\n"
              + "CFLAGS=" + cflags + "\n"
              + "LDFLAGS=" + ldflags + "\n")
    if (marker_path.is_file() and marker_path.read_text() == marker
            and validate_awk(executable)):
        return executable

    work = build_dir / "bootstrap" / "gawk"
    shutil.rmtree(work, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
    source = work / "source"
    objects = work / "build"
    stage_source(revision, source)
    objects.mkdir(parents=True, exist_ok=True)

    for required in ("configure", "Makefile.in", "awkgram.c",
                     "command.c", "support/Makefile.in"):
        if not (source / required).is_file():
            raise RuntimeError("pinned Gawk lacks generated input " + required)

    # Pre-generated GNU Autoconf/Automake and Bison artifacts are part of
    # this fork. Avoid rebuilding tool generators merely due to Git timestamps.
    for name in ("configure", "Makefile.in", "configh.in",
                 "support/Makefile.in", "awkgram.c", "command.c"):
        path = source / name
        if path.exists():
            path.touch()

    env = clean_host_environment(os.environ)
    env["CC"] = cc
    env["CC_FOR_BUILD"] = cc
    env["MAKE"] = str(make_path)
    env["AWK"] = seed
    env["WHP_AWK_SEED"] = seed
    env["WHP_AWK_LOCKED"] = "1"
    if sdk:
        env["SDKROOT"] = sdk
    if cflags:
        env["CFLAGS"] = cflags
    if ldflags:
        env["LDFLAGS"] = ldflags
    # Gawk is used as a host command; target architecture and flags are
    # deliberately not inherited by its configure and make invocations.
    command(["/bin/sh", str(source / "configure"),
             f"--prefix={prefix}", "--disable-nls"],
            cwd=objects, env=env)
    command([str(make_path), "-C", str(objects / "support"), "libsupport.a"],
            cwd=objects, env=env)
    command([str(make_path), "-C", str(objects), "gawk"],
            cwd=objects, env=env)
    built = objects / "gawk"
    if not validate_awk(built):
        raise RuntimeError("built Gawk failed native AWK semantic probes")
    (prefix / "bin").mkdir(parents=True, exist_ok=True)
    shutil.copy2(built, executable)
    executable.chmod(executable.stat().st_mode | 0o111)
    if not validate_awk(executable):
        raise RuntimeError("installed Gawk failed native AWK semantic probes")
    marker_path.write_text(marker)
    return executable


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args()
    try:
        print(bootstrap(pathlib.Path(args.build_dir).expanduser().resolve()))
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"error: WHP managed Gawk bootstrap failed: {exc}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
