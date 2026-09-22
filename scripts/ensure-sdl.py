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
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/sdl")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SDL_BOOTSTRAP_SCHEMA = "1"
SDL_MIN_VERSION = (3, 2, 0)


def run_text(command: List[str], cwd: pathlib.Path | None = None) -> str:
    completed = subprocess.run(
        command,
        cwd=cwd,
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


def run_logged(command: List[str], cwd: pathlib.Path | None = None) -> None:
    completed = subprocess.run(
        command,
        cwd=cwd,
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
        SUBMODULE_DIR / "CMakeLists.txt",
        SUBMODULE_DIR / "include" / "SDL3" / "SDL_version.h",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled SDL source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/sdl or use a Git checkout"
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


def ensure_sdl_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(f"SDL gitlink is not registered in QEMU: {SUBMODULE_REL}")
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
        run_logged(
            [
                "git",
                "-C",
                str(ROOT),
                "submodule",
                "update",
                "--init",
                "--depth",
                "1",
                str(SUBMODULE_REL),
            ]
        )
        current_revision = run_text(
            ["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"]
        )

    if current_revision != expected_revision:
        raise RuntimeError(
            "bundled SDL checkout does not match the QEMU gitlink: "
            f"{current_revision} != {expected_revision}"
        )

    dirty = run_text(
        [
            "git",
            "-C",
            str(SUBMODULE_DIR),
            "status",
            "--porcelain",
            "--untracked-files=no",
        ]
    )
    if dirty:
        raise RuntimeError(
            "bundled SDL submodule has tracked changes; commit them in the SDL fork "
            "and update the QEMU gitlink"
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
    raise RuntimeError(f"{name} is required to bootstrap bundled SDL3")


def select_c_compiler() -> str:
    requested = os.environ.get("CC")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("CC must name exactly one executable for SDL bootstrap")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"CC is not executable: {candidate}")

    if platform.system() == "Darwin" and shutil.which("xcrun"):
        candidate = run_text(["xcrun", "--sdk", "macosx", "--find", "clang"])
        if candidate:
            return candidate

    for name in ("cc", "clang", "gcc"):
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError("a host C compiler is required to bootstrap bundled SDL3")


def compiler_version(cc: str) -> str:
    completed = subprocess.run(
        [cc, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    first = completed.stdout.splitlines()[0] if completed.stdout else ""
    if completed.returncode != 0 or not first:
        raise RuntimeError(f"could not identify SDL bootstrap compiler: {cc}")
    return first


def cmake_version(cmake: str) -> str:
    output = run_text([cmake, "--version"])
    return output.splitlines()[0] if output else ""


def ninja_version(ninja: str) -> str:
    return run_text([ninja, "--version"])


def macos_sdkroot() -> str:
    if platform.system() != "Darwin":
        return ""
    requested = os.environ.get("SDKROOT")
    if requested:
        return requested
    if not shutil.which("xcrun"):
        raise RuntimeError("xcrun is required to locate the macOS SDK for SDL3")
    return run_text(["xcrun", "--sdk", "macosx", "--show-sdk-path"])


def macos_arch() -> str:
    if platform.system() != "Darwin":
        return ""
    requested = os.environ.get("SDL_MACOS_ARCH", "auto")
    if requested == "auto":
        machine = platform.machine().lower()
        if machine in ("aarch64", "arm64"):
            return "arm64"
        if machine in ("amd64", "x86_64"):
            return "x86_64"
        raise RuntimeError(f"unsupported macOS architecture for SDL3: {machine}")
    if requested not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(
            "SDL_MACOS_ARCH must be auto, arm64, arm64e, or x86_64: "
            f"{requested}"
        )
    return requested


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


def system_sdl3_usable() -> bool:
    pkg_config = shutil.which("pkg-config") or shutil.which("pkgconf")
    if not pkg_config:
        return False
    completed = subprocess.run(
        [pkg_config, "--atleast-version=3.2.0", "sdl3"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def find_pkgconfig_file(prefix: pathlib.Path) -> pathlib.Path | None:
    candidates = (
        prefix / "lib" / "pkgconfig" / "sdl3.pc",
        prefix / "lib64" / "pkgconfig" / "sdl3.pc",
        prefix / "libdata" / "pkgconfig" / "sdl3.pc",
    )
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    for candidate in prefix.glob("**/pkgconfig/sdl3.pc"):
        if candidate.is_file():
            return candidate
    return None


def installed_version(pc_file: pathlib.Path) -> str:
    for line in pc_file.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith("Version:"):
            return line.split(":", 1)[1].strip()
    return ""


def marker_text(
    revision: str,
    cmake: str,
    cmake_id: str,
    ninja: str,
    ninja_id: str,
    cc: str,
    cc_id: str,
    sdkroot: str,
    arch: str,
) -> str:
    return (
        f"SDL_BOOTSTRAP_SCHEMA={SDL_BOOTSTRAP_SCHEMA}\n"
        f"SOURCE_DIR={ROOT}\n"
        f"SDL_GIT_COMMIT={revision}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"CMAKE={cmake}\n"
        f"CMAKE_VERSION={cmake_id}\n"
        f"NINJA={ninja}\n"
        f"NINJA_VERSION={ninja_id}\n"
        f"CC={cc}\n"
        f"CC_VERSION={cc_id}\n"
        f"SDKROOT={sdkroot}\n"
        f"SDL_MACOS_ARCH={arch}\n"
        "SDL_SHARED=OFF\n"
        "SDL_STATIC=ON\n"
    )


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-sdl-bootstrap"
    if not marker_file.is_file():
        return False
    if marker_file.read_text(encoding="utf-8", errors="replace") != marker:
        return False
    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        return False
    return version_tuple(installed_version(pc_file)) >= SDL_MIN_VERSION


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision = ensure_sdl_source()
    cmake = command_path("cmake", "CMAKE")
    ninja = command_path("ninja", "NINJA_CMD")
    cc = select_c_compiler()
    sdkroot = macos_sdkroot()
    arch = macos_arch()

    cmake_id = cmake_version(cmake)
    ninja_id = ninja_version(ninja)
    cc_id = compiler_version(cc)

    work_dir = build_root / "bootstrap" / "sdl3"
    prefix = build_root / "deps" / "sdl3"
    marker = marker_text(
        revision,
        cmake,
        cmake_id,
        ninja,
        ninja_id,
        cc,
        cc_id,
        sdkroot,
        arch,
    )
    if cache_valid(prefix, marker):
        return prefix

    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
    work_dir.parent.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    command = [
        cmake,
        "-S",
        str(SUBMODULE_DIR),
        "-B",
        str(work_dir),
        "-G",
        "Ninja",
        f"-DCMAKE_MAKE_PROGRAM={ninja}",
        f"-DCMAKE_C_COMPILER={cc}",
        f"-DCMAKE_INSTALL_PREFIX={prefix}",
        "-DCMAKE_BUILD_TYPE=Release",
        "-DSDL_SHARED=OFF",
        "-DSDL_STATIC=ON",
        "-DSDL_INSTALL=ON",
        "-DSDL_TEST_LIBRARY=OFF",
        "-DSDL_TESTS=OFF",
        "-DSDL_EXAMPLES=OFF",
    ]
    if sdkroot:
        command.append(f"-DCMAKE_OSX_SYSROOT={sdkroot}")
    if arch:
        command.append(f"-DCMAKE_OSX_ARCHITECTURES={arch}")

    print(f"WHP SDL3 bootstrap: {revision} -> {prefix}", file=sys.stderr)
    run_logged(command)
    run_logged([ninja, "-C", str(work_dir), "install"])

    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        raise RuntimeError(f"SDL3 bootstrap did not install sdl3.pc under {prefix}")
    version = installed_version(pc_file)
    if version_tuple(version) < SDL_MIN_VERSION:
        raise RuntimeError(
            f"bootstrapped SDL3 is too old for QEMU: {version or '<unknown>'} < 3.2.0"
        )

    (prefix / ".whp-sdl-bootstrap").write_text(marker, encoding="utf-8")
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    if args.mode == "auto" and system_sdl3_usable():
        print("WHP SDL3 bootstrap: host SDL3 >= 3.2.0 is usable", file=sys.stderr)
        return 0

    try:
        prefix = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.mode == "auto":
            print(f"warning: optional WHP SDL3 bootstrap skipped: {exc}", file=sys.stderr)
            return 0
        print(f"error: WHP SDL3 bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
