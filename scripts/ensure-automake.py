#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP GNU Automake as a host-side generator.

Automake's Git bootstrap is deliberately self-hosting: it creates temporary
aclocal/automake scripts from its own sources, so an installed Automake is not
needed.  It does require a small seed tool set (sed, Perl, Autoconf, GNU Make).
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tarfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/automake")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SED_ADAPTER = ROOT / "sed.sh"
AUTOMAKE_BOOTSTRAP_SCHEMA = "2"


def run_text(
    command: List[str],
    *,
    cwd: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed: {shlex.join(command)}"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def run_logged(
    command: List[str],
    *,
    cwd: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
        env=env,
        stdout=sys.stderr,
        stderr=sys.stderr,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit status {completed.returncode}: "
            + shlex.join(command)
        )


def executable(candidate: str) -> str | None:
    if not candidate:
        return None
    path = (
        candidate
        if pathlib.Path(candidate).is_absolute()
        else shutil.which(candidate)
    )
    if path and pathlib.Path(path).is_file() and os.access(path, os.X_OK):
        return os.path.abspath(path)
    return None


def explicit_tool(env_name: str) -> str | None:
    value = os.environ.get(env_name, "")
    if not value:
        return None
    argv = shlex.split(value)
    if len(argv) != 1:
        raise RuntimeError(f"{env_name} must name exactly one executable")
    path = executable(argv[0])
    if not path:
        raise RuntimeError(f"{env_name} is not executable: {argv[0]}")
    return path


def tool(name: str, env_name: str | None = None, aliases: tuple[str, ...] = ()) -> str:
    requested = explicit_tool(env_name) if env_name else None
    if requested:
        return requested
    for candidate in (name, *aliases):
        path = executable(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap GNU Automake")


def select_gnu_make() -> str:
    requested = explicit_tool("MAKE_CMD") or explicit_tool("MAKE")
    candidates: list[str] = []
    if requested:
        candidates.append(requested)
    else:
        for name in ("gmake", "make"):
            path = executable(name)
            if path and path not in candidates:
                candidates.append(path)

    for path in candidates:
        completed = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode == 0 and "GNU Make" in completed.stdout:
            return path
    raise RuntimeError("GNU Make is required to bootstrap GNU Automake")


def select_seed_sed() -> str:
    if not SED_ADAPTER.is_file() or not os.access(SED_ADAPTER, os.X_OK):
        raise RuntimeError(f"QEMU sed seed adapter is unavailable: {SED_ADAPTER}")

    env = os.environ.copy()
    requested = os.environ.get("WHP_AUTOMAKE_SED_SEED", "")
    if requested:
        env["WHP_SED_SEED"] = requested
    completed = subprocess.run(
        [str(SED_ADAPTER), "--print-seed"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    seed = completed.stdout.strip()
    if completed.returncode != 0 or not seed:
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU sed.sh could not resolve the Automake bootstrap seed"
            + (f": {detail}" if detail else "")
        )
    return seed


def first_line(command: List[str]) -> str:
    output = run_text(command)
    return output.splitlines()[0] if output else ""


def tolerant_identity(command: List[str]) -> str:
    completed = subprocess.run(
        command,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    first = output.splitlines()[0] if output else "<no version output>"
    return f"exit={completed.returncode}: {first}"


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def gitlink_revision() -> str:
    line = run_text([
        "git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL),
    ])
    fields = line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"Automake gitlink is not registered in QEMU: {SUBMODULE_REL}"
        )
    return fields[2]


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "bootstrap",
        SUBMODULE_DIR / "configure.ac",
        SUBMODULE_DIR / "Makefile.am",
        SUBMODULE_DIR / "bin" / "automake.in",
        SUBMODULE_DIR / "bin" / "aclocal.in",
    )
    for path in candidates:
        if not path.is_file():
            raise RuntimeError(
                f"bundled Automake source is unavailable: {SUBMODULE_DIR}"
            )
    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "archive-" + digest.hexdigest()


def ensure_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    revision = gitlink_revision()
    current = ""
    if (SUBMODULE_DIR / ".git").exists():
        try:
            current = run_text([
                "git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD",
            ])
        except RuntimeError:
            current = ""

    if current != revision:
        run_logged([
            "git", "-C", str(ROOT), "submodule", "update", "--init",
            "--depth", "1", str(SUBMODULE_REL),
        ])
        current = run_text([
            "git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD",
        ])
    if current != revision:
        raise RuntimeError(
            f"Automake submodule revision mismatch: {current} != {revision}"
        )

    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        raise RuntimeError(
            "Automake submodule has tracked changes; commit them in the "
            "Automake fork and update the QEMU gitlink"
        )
    return revision


def copy_source(revision: str, destination: pathlib.Path) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)

    if git_checkout_available() and (SUBMODULE_DIR / ".git").exists():
        completed = subprocess.run(
            [
                "git", "-C", str(SUBMODULE_DIR),
                "archive", "--format=tar", revision,
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0:
            detail = completed.stderr.decode("utf-8", errors="replace").strip()
            raise RuntimeError(
                f"could not archive Automake revision {revision}"
                + (f": {detail}" if detail else "")
            )
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(
            fileobj=io.BytesIO(completed.stdout), mode="r:"
        ) as archive:
            archive.extractall(destination)
    else:
        shutil.copytree(
            SUBMODULE_DIR,
            destination,
            ignore=shutil.ignore_patterns(".git"),
        )

    # Automake's bootstrap intentionally checks only that a .git directory is
    # present; its own comment explicitly permits this for non-checkout trees.
    (destination / ".git").mkdir(exist_ok=True)


def automake_pair_usable(prefix: pathlib.Path) -> bool:
    automake = prefix / "bin" / "automake"
    aclocal = prefix / "bin" / "aclocal"
    for path, marker in (
        (automake, "GNU automake"),
        (aclocal, "GNU automake"),
    ):
        if not path.is_file() or not os.access(path, os.X_OK):
            return False
        completed = subprocess.run(
            [str(path), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0 or marker not in completed.stdout:
            return False
    return True


def marker_text(
    revision: str,
    seed: str,
    perl: str,
    autoconf: str,
    autom4te: str,
    make: str,
) -> str:
    return (
        f"AUTOMAKE_BOOTSTRAP_SCHEMA={AUTOMAKE_BOOTSTRAP_SCHEMA}\n"
        f"AUTOMAKE_GIT_COMMIT={revision}\n"
        f"SEED_SED={seed}: {tolerant_identity([seed, '--version'])}\n"
        f"PERL={perl}: {first_line([perl, '--version'])}\n"
        f"AUTOCONF={autoconf}: {first_line([autoconf, '--version'])}\n"
        f"AUTOM4TE={autom4te}: {first_line([autom4te, '--version'])}\n"
        f"MAKE={make}: {first_line([make, '--version'])}\n"
    )


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision = ensure_source()
    seed = select_seed_sed()
    perl = tool("perl", "PERL")
    autoconf = tool("autoconf", "AUTOCONF")
    autom4te = tool("autom4te", "AUTOM4TE")
    make = select_gnu_make()

    prefix = build_root / "deps" / "automake"
    work = build_root / "bootstrap" / "automake"
    source = work / "source"
    objects = work / "build"
    marker_path = prefix / ".whp-automake-bootstrap"

    marker = marker_text(
        revision, seed, perl, autoconf, autom4te, make
    )
    if (
        marker_path.is_file()
        and marker_path.read_text(encoding="utf-8", errors="replace") == marker
        and automake_pair_usable(prefix)
    ):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, source)
    objects.mkdir(parents=True, exist_ok=True)

    seed_bin = work / "seed-bin"
    seed_bin.mkdir(parents=True, exist_ok=True)
    seed_link = seed_bin / "sed"
    try:
        seed_link.symlink_to(SED_ADAPTER)
    except OSError:
        shutil.copy2(SED_ADAPTER, seed_link)
        seed_link.chmod(seed_link.stat().st_mode | 0o111)

    env = os.environ.copy()
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT",
        "AUTOMAKE", "ACLOCAL",
    ):
        env.pop(key, None)
    env["PERL"] = perl
    env["AUTOCONF"] = autoconf
    env["AUTOM4TE"] = autom4te
    env["WHP_SED_SEED"] = seed
    env["SED"] = str(SED_ADAPTER)
    env["PATH"] = str(seed_bin) + os.pathsep + env.get("PATH", "")

    config_shell = explicit_tool("CONFIG_SHELL") or "/bin/sh"

    print(
        f"WHP Automake bootstrap: {revision} -> {prefix} "
        f"(seed sed {seed})",
        file=sys.stderr,
    )
    run_logged(
        [config_shell, str(source / "bootstrap")],
        cwd=source,
        env=env,
    )
    configure = source / "configure"
    if not configure.is_file():
        raise RuntimeError("Automake bootstrap did not generate configure")

    run_logged(
        [config_shell, str(configure), f"--prefix={prefix}"],
        cwd=objects,
        env=env,
    )
    run_logged(
        [make, "-j", str(max(1, os.cpu_count() or 1))],
        cwd=objects,
        env=env,
    )
    run_logged([make, "install"], cwd=objects, env=env)

    if not automake_pair_usable(prefix):
        raise RuntimeError(
            f"bootstrapped Automake/aclocal pair is not usable: {prefix}"
        )
    marker_path.write_text(marker, encoding="utf-8")
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args(argv)
    try:
        prefix = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP Automake bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
