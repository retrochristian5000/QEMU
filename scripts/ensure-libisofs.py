#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/libisofs")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
LIBISOFS_BOOTSTRAP_SCHEMA = "1"
LIBISOFS_MIN_VERSION = (1, 1, 2)
PKG_NAME = "libisofs-1"


def run_text(command: List[str], *, cwd: pathlib.Path | None = None,
             env: dict[str, str] | None = None) -> str:
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
            f"command failed: {' '.join(command)}"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def run_logged(command: List[str], *, cwd: pathlib.Path | None = None,
               env: dict[str, str] | None = None) -> None:
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
            + " ".join(command)
        )


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "configure.ac",
        SUBMODULE_DIR / "libisofs" / "libisofs.h",
        SUBMODULE_DIR / "libisofs" / "messages.c",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled libisofs source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/libisofs or use a Git checkout"
        )
    digest = hashlib.sha256()
    for path in candidates:
        if path.is_file():
            digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
            digest.update(b"\0")
            digest.update(path.read_bytes())
            digest.update(b"\0")
    return f"archive-{digest.hexdigest()}"


def ensure_libisofs_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"libisofs gitlink is not registered in QEMU: {SUBMODULE_REL}"
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
            "bundled libisofs checkout does not match the QEMU gitlink: "
            f"{current_revision} != {expected_revision}"
        )

    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        raise RuntimeError(
            "bundled libisofs submodule has tracked changes; commit them in "
            "the libisofs fork and update the QEMU gitlink"
        )
    return expected_revision


def command_path(name: str, env_name: str | None = None) -> str:
    requested = os.environ.get(env_name, "") if env_name else ""
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"{env_name} is not executable: {candidate}")

    path = shutil.which(name)
    if path:
        return path
    raise RuntimeError(f"{name} is required to bootstrap bundled libisofs")


def select_c_compiler() -> str:
    requested = os.environ.get("CC")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("CC must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"CC is not executable: {candidate}")

    if platform.system() == "Darwin" and shutil.which("xcrun"):
        return run_text(["xcrun", "--sdk", "macosx", "--find", "clang"])

    for name in ("clang", "cc", "gcc"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("a host C compiler is required to bootstrap libisofs")


def compiler_version(cc: str) -> str:
    output = run_text([cc, "--version"])
    return output.splitlines()[0] if output else ""


def version_tuple(value: str) -> tuple[int, ...]:
    pieces = []
    for part in value.strip().split("."):
        digits = ""
        for character in part:
            if character.isdigit():
                digits += character
            else:
                break
        if not digits:
            break
        pieces.append(int(digits))
    return tuple(pieces)


def pkg_config() -> str | None:
    return shutil.which("pkg-config") or shutil.which("pkgconf")


def strict_header_probe(cc: str, pkgconf: str) -> bool:
    if subprocess.run(
        [pkgconf, "--atleast-version=1.1.2", PKG_NAME],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        return False

    try:
        cflags = shlex.split(run_text([pkgconf, "--cflags", PKG_NAME]))
    except RuntimeError:
        return False

    source = """#include <libisofs.h>
int main(void)
{
    return 0;
}
"""
    with tempfile.TemporaryDirectory(prefix="qemu-libisofs-probe-") as tmp:
        probe = pathlib.Path(tmp) / "probe.c"
        probe.write_text(source, encoding="utf-8")
        completed = subprocess.run(
            [cc, "-std=gnu11", "-Werror=strict-prototypes", "-fsyntax-only",
             *cflags, str(probe)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0


def system_libisofs_usable(cc: str) -> bool:
    pkgconf = pkg_config()
    return bool(pkgconf and strict_header_probe(cc, pkgconf))


def find_pkgconfig_file(prefix: pathlib.Path) -> pathlib.Path | None:
    for candidate in (
        prefix / "lib" / "pkgconfig" / "libisofs-1.pc",
        prefix / "lib64" / "pkgconfig" / "libisofs-1.pc",
        prefix / "libdata" / "pkgconfig" / "libisofs-1.pc",
    ):
        if candidate.is_file():
            return candidate
    for candidate in prefix.glob("**/pkgconfig/libisofs-1.pc"):
        if candidate.is_file():
            return candidate
    return None


def installed_version(pc_file: pathlib.Path) -> str:
    for line in pc_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return ""


def macos_settings() -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

    sdkroot = os.environ.get("SDKROOT", "")
    if not sdkroot:
        sdkroot = run_text(["xcrun", "--sdk", "macosx", "--show-sdk-path"])

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
        raise RuntimeError(f"unsupported WHP_MACOS_ARCH for libisofs: {arch}")

    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        pieces = version.split(".")
        deployment = ".".join(pieces[:2]) if version else "11.0"

    return sdkroot, arch, deployment


def append_flags(current: str, values: list[str]) -> str:
    parts = [current.strip()] if current.strip() else []
    parts.extend(values)
    return " ".join(parts)


def marker_text(revision: str, cc: str, cc_id: str, sdkroot: str,
                arch: str, deployment: str) -> str:
    return (
        f"LIBISOFS_BOOTSTRAP_SCHEMA={LIBISOFS_BOOTSTRAP_SCHEMA}\n"
        f"LIBISOFS_GIT_COMMIT={revision}\n"
        f"CC={cc}\n"
        f"CC_VERSION={cc_id}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
        "STRICT_PROTOTYPES=1\n"
        "SHARED=0\n"
        "STATIC=1\n"
    )


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-libisofs-bootstrap"
    if not marker_file.is_file():
        return False
    if marker_file.read_text(encoding="utf-8", errors="replace") != marker:
        return False
    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        return False
    return version_tuple(installed_version(pc_file)) >= LIBISOFS_MIN_VERSION


def bootstrap(build_root: pathlib.Path, cc: str) -> pathlib.Path:
    revision = ensure_libisofs_source()
    make = command_path("make", "MAKE")
    sdkroot, arch, deployment = macos_settings()
    cc_id = compiler_version(cc)

    work_dir = build_root / "bootstrap" / "libisofs"
    source_copy = work_dir / "source"
    object_dir = work_dir / "build"
    prefix = build_root / "deps" / "libisofs"
    marker = marker_text(revision, cc, cc_id, sdkroot, arch, deployment)
    if cache_valid(prefix, marker):
        return prefix

    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SUBMODULE_DIR,
        source_copy,
        ignore=shutil.ignore_patterns(".git"),
    )

    env = os.environ.copy()
    env["CC"] = cc
    compile_flags = ["-O3", "-Werror=strict-prototypes"]
    link_flags: list[str] = []
    if sdkroot:
        compile_flags += [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
        link_flags += [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
        env["SDKROOT"] = sdkroot
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment

    env["CFLAGS"] = append_flags(env.get("CFLAGS", ""), compile_flags)
    env["LDFLAGS"] = append_flags(env.get("LDFLAGS", ""), link_flags)

    print(
        f"WHP libisofs bootstrap: {revision} -> {prefix}",
        file=sys.stderr,
    )
    run_logged(["/bin/sh", "bootstrap"], cwd=source_copy, env=env)

    object_dir.mkdir(parents=True, exist_ok=True)
    configure = source_copy / "configure"
    run_logged([
        str(configure),
        f"--prefix={prefix}",
        "--disable-shared",
        "--enable-static",
        "--disable-libacl",
        "--disable-libjte",
        "--disable-ldconfig-at-install",
    ], cwd=object_dir, env=env)
    run_logged([make, "-j", str(max(1, os.cpu_count() or 1))],
               cwd=object_dir, env=env)
    run_logged([make, "install"], cwd=object_dir, env=env)

    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        raise RuntimeError(
            f"libisofs bootstrap did not install libisofs-1.pc under {prefix}"
        )
    version = installed_version(pc_file)
    if version_tuple(version) < LIBISOFS_MIN_VERSION:
        raise RuntimeError(
            f"bootstrapped libisofs is too old: "
            f"{version or '<unknown>'} < 1.1.2"
        )

    pkgconf = pkg_config()
    if pkgconf:
        probe_env = os.environ.copy()
        pc_dir = str(pc_file.parent)
        probe_env["PKG_CONFIG_PATH"] = (
            pc_dir
            + (":" + probe_env["PKG_CONFIG_PATH"]
               if probe_env.get("PKG_CONFIG_PATH") else "")
        )
        old_path = os.environ.get("PKG_CONFIG_PATH")
        os.environ["PKG_CONFIG_PATH"] = probe_env["PKG_CONFIG_PATH"]
        try:
            if not strict_header_probe(cc, pkgconf):
                raise RuntimeError(
                    "bootstrapped libisofs failed the Clang strict-prototype probe"
                )
        finally:
            if old_path is None:
                os.environ.pop("PKG_CONFIG_PATH", None)
            else:
                os.environ["PKG_CONFIG_PATH"] = old_path

    (prefix / ".whp-libisofs-bootstrap").write_text(marker, encoding="utf-8")
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    try:
        cc = select_c_compiler()
        if args.mode == "auto" and system_libisofs_usable(cc):
            print(
                "WHP libisofs bootstrap: host libisofs >= 1.1.2 passes "
                "-Wstrict-prototypes",
                file=sys.stderr,
            )
            return 0

        prefix = bootstrap(
            pathlib.Path(args.build_dir).expanduser().resolve(), cc
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.mode == "auto":
            print(
                f"warning: optional WHP libisofs bootstrap skipped: {exc}",
                file=sys.stderr,
            )
            return 0
        print(f"error: WHP libisofs bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
