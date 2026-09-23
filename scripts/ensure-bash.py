#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/bash")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
BASH_BOOTSTRAP_SCHEMA = "2"


def run_text(
    command: List[str],
    *,
    cwd: pathlib.Path | None = None,
    env: dict[str, str] | None = None,
) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed: {' '.join(command)}"
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
        command, cwd=cwd, env=env,
        stdout=sys.stderr, stderr=sys.stderr, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit status {completed.returncode}: "
            + " ".join(command)
        )


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "configure",
        SUBMODULE_DIR / "Makefile.in",
        SUBMODULE_DIR / "version.c",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled Bash source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/bash or use a Git checkout"
        )
    digest = hashlib.sha256()
    for path in candidates:
        if not path.is_file():
            continue
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"archive-{digest.hexdigest()}"


def copy_bash_source(revision: str, destination: pathlib.Path) -> None:
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
            detail = completed.stderr.decode(
                "utf-8", errors="replace"
            ).strip()
            raise RuntimeError(
                f"could not archive pinned Bash revision {revision}"
                + (f": {detail}" if detail else "")
            )
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(
            fileobj=io.BytesIO(completed.stdout), mode="r:"
        ) as archive:
            archive.extractall(destination)
        return

    shutil.copytree(
        SUBMODULE_DIR,
        destination,
        ignore=shutil.ignore_patterns(".git"),
    )


def ensure_bash_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"Bash gitlink is not registered in QEMU: {SUBMODULE_REL}"
        )
    expected_revision = fields[2]

    current_revision = ""
    if (SUBMODULE_DIR / ".git").exists():
        try:
            current_revision = run_text(
                ["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"]
            )
        except RuntimeError:
            current_revision = ""

    if current_revision != expected_revision:
        run_logged([
            "git", "-C", str(ROOT), "submodule", "update", "--init",
            "--depth", "1", str(SUBMODULE_REL),
        ])
        current_revision = run_text(
            ["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"]
        )

    if current_revision != expected_revision:
        raise RuntimeError(
            "bundled Bash checkout does not match the QEMU gitlink: "
            f"{current_revision} != {expected_revision}"
        )

    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        print(
            "WHP Bash bootstrap: tracked submodule changes are preserved "
            "and excluded from the pinned build:\n" + dirty,
            file=sys.stderr,
        )
    return expected_revision


def command_path(name: str, env_name: str | None = None) -> str:
    requested = os.environ.get(env_name, "") if env_name else ""
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
        path = (
            candidate
            if pathlib.Path(candidate).is_absolute()
            else shutil.which(candidate)
        )
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"{env_name} is not executable: {candidate}")

    names = ("gmake", "make") if name == "make" else (name,)
    for candidate in names:
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap bundled Bash")


def select_c_compiler() -> str:
    requested = os.environ.get("CC", "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) == 1:
            candidate = argv[0]
            path = (
                candidate
                if pathlib.Path(candidate).is_absolute()
                else shutil.which(candidate)
            )
            if path and pathlib.Path(path).exists():
                return str(path)

    if platform.system() == "Darwin" and shutil.which("xcrun"):
        return run_text(["xcrun", "--sdk", "macosx", "--find", "clang"])

    for name in ("cc", "clang", "gcc"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("a host C compiler is required to bootstrap Bash")


def compiler_version(cc: str) -> str:
    output = run_text([cc, "--version"])
    return output.splitlines()[0] if output else ""


def macos_settings() -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

    if not shutil.which("xcrun"):
        raise RuntimeError("xcrun is required to locate the macOS SDK for Bash")
    sdkroot = os.environ.get("SDKROOT") or run_text(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"]
    )
    if not pathlib.Path(sdkroot).is_dir():
        raise RuntimeError(f"macOS SDK does not exist: {sdkroot}")

    arch = os.environ.get("WHP_MACOS_ARCH", "auto")
    if arch == "auto":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            arch = "arm64"
        elif machine in ("x86_64", "amd64"):
            arch = "x86_64"
        else:
            raise RuntimeError(f"unsupported macOS architecture: {machine}")
    if arch not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(f"unsupported WHP_MACOS_ARCH for Bash: {arch}")

    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        parts = version.split(".")
        deployment = ".".join(parts[:2]) if version else "11.0"

    return sdkroot, arch, deployment


def bash_usable(path: pathlib.Path) -> bool:
    if not path.is_file():
        return False
    completed = subprocess.run(
        [
            str(path), "--noprofile", "--norc", "-c",
            'test -n "$BASH_VERSION" && '
            '(( BASH_VERSINFO[0] > 3 || '
            '(BASH_VERSINFO[0] == 3 && BASH_VERSINFO[1] >= 2) ))',
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def marker_text(
    revision: str,
    cc: str,
    sdkroot: str,
    arch: str,
    deployment: str,
) -> str:
    return (
        f"BASH_BOOTSTRAP_SCHEMA={BASH_BOOTSTRAP_SCHEMA}\n"
        f"BASH_GIT_COMMIT={revision}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"CC={cc}\n"
        f"CC_VERSION={compiler_version(cc)}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
        "BASH_MALLOC=system\n"
        "NLS=disabled\n"
    )


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision = ensure_bash_source()
    cc = select_c_compiler()
    make = command_path("make", "MAKE")
    sdkroot, arch, deployment = macos_settings()

    prefix = build_root / "deps" / "bash"
    work_dir = build_root / "bootstrap" / "bash"
    source_copy = work_dir / "source"
    object_dir = work_dir / "build"
    marker = marker_text(revision, cc, sdkroot, arch, deployment)
    marker_file = prefix / ".whp-bash-bootstrap"
    bash_path = prefix / "bin" / "bash"

    if (
        marker_file.is_file()
        and marker_file.read_text(encoding="utf-8", errors="replace") == marker
        and bash_usable(bash_path)
    ):
        return bash_path

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    copy_bash_source(revision, source_copy)
    object_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # INSTALL is an Autoconf/Make command variable, not WHP build policy.
    env.pop("INSTALL", None)
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT", "SHELLOPTS", "BASHOPTS",
        "CFLAGS", "CPPFLAGS", "LDFLAGS",
    ):
        env.pop(key, None)
    env["CC"] = cc

    if sdkroot:
        flags = shlex.join([
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ])
        env["CFLAGS"] = flags
        env["LDFLAGS"] = flags
        env["SDKROOT"] = sdkroot
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment

    configure = source_copy / "configure"
    print(f"WHP Bash bootstrap: {revision} -> {prefix}", file=sys.stderr)
    run_logged([
        "/bin/sh", str(configure), f"--prefix={prefix}",
        "--without-bash-malloc", "--disable-nls",
    ], cwd=object_dir, env=env)
    run_logged(
        [make, "-j", str(max(1, os.cpu_count() or 1))],
        cwd=object_dir, env=env,
    )
    run_logged([make, "install"], cwd=object_dir, env=env)

    if not bash_usable(bash_path):
        raise RuntimeError(f"bootstrapped Bash is not usable: {bash_path}")
    marker_file.write_text(marker, encoding="utf-8")
    return bash_path


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args(argv)

    try:
        path = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP Bash bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
