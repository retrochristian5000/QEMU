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
SUBMODULE_REL = pathlib.Path("toolchains/jack")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
JACK_BOOTSTRAP_SCHEMA = "2"


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


def run_logged(
    command: List[str],
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
            + " ".join(command)
        )


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "wscript",
        SUBMODULE_DIR / "jack.pc.in",
        SUBMODULE_DIR / "common" / "jack" / "jack.h",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled JACK source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/jack or use a Git checkout"
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


def ensure_jack_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(f"JACK gitlink is not registered in QEMU: {SUBMODULE_REL}")
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
            "bundled JACK checkout does not match the QEMU gitlink: "
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
            "bundled JACK submodule has tracked changes; commit them in the JACK "
            "fork and update the QEMU gitlink"
        )
    return expected_revision


def command_path(value: str, env_name: str, fallbacks: tuple[str, ...]) -> str:
    requested = os.environ.get(env_name, "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"{env_name} is not executable: {candidate}")

    if platform.system() == "Darwin" and shutil.which("xcrun"):
        found = run_text(["xcrun", "--sdk", "macosx", "--find", value])
        if found:
            return found

    for name in fallbacks:
        path = shutil.which(name)
        if path:
            return path
    raise RuntimeError(f"a host {env_name} compiler is required to bootstrap JACK")


def compiler_id(path: str) -> str:
    output = run_text([path, "--version"])
    return output.splitlines()[0] if output else ""


def macos_settings() -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

    sdkroot = os.environ.get("SDKROOT", "")
    if not sdkroot:
        if not shutil.which("xcrun"):
            raise RuntimeError(
                "xcrun is required to locate the macOS SDK for JACK"
            )
        sdkroot = run_text(["xcrun", "--sdk", "macosx", "--show-sdk-path"])
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
        raise RuntimeError(f"unsupported WHP_MACOS_ARCH for JACK: {arch}")

    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        pieces = version.split(".")
        deployment = ".".join(pieces[:2]) if version else "11.0"

    return sdkroot, arch, deployment


def system_jack_usable() -> bool:
    pkg_config = shutil.which("pkg-config") or shutil.which("pkgconf")
    if not pkg_config:
        return False
    completed = subprocess.run(
        [pkg_config, "--exists", "jack"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def find_pkgconfig_file(prefix: pathlib.Path) -> pathlib.Path | None:
    for candidate in (
        prefix / "lib" / "pkgconfig" / "jack.pc",
        prefix / "lib64" / "pkgconfig" / "jack.pc",
        prefix / "libdata" / "pkgconfig" / "jack.pc",
    ):
        if candidate.is_file():
            return candidate
    return None


def marker_text(
    revision: str,
    cc: str,
    cxx: str,
    sdkroot: str,
    arch: str,
    deployment: str,
) -> str:
    return (
        f"JACK_BOOTSTRAP_SCHEMA={JACK_BOOTSTRAP_SCHEMA}\n"
        f"JACK_GIT_COMMIT={revision}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"CC={cc}\n"
        f"CC_VERSION={compiler_id(cc)}\n"
        f"CXX={cxx}\n"
        f"CXX_VERSION={compiler_id(cxx)}\n"
        f"PYTHON={sys.executable}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
        "JACK_CLIENT_ONLY=1\n"
    )


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-jack-bootstrap"
    return (
        marker_file.is_file()
        and marker_file.read_text(encoding="utf-8", errors="replace") == marker
        and find_pkgconfig_file(prefix) is not None
        and (prefix / "include" / "jack" / "jack.h").is_file()
    )


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision = ensure_jack_source()
    cc = command_path("clang", "CC", ("cc", "clang", "gcc"))
    cxx = command_path("clang++", "CXX", ("c++", "clang++", "g++"))
    prefix = build_root / "deps" / "jack"
    sdkroot, arch, deployment = macos_settings()
    marker = marker_text(revision, cc, cxx, sdkroot, arch, deployment)
    if cache_valid(prefix, marker):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(SUBMODULE_DIR / "build", ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    # Do not leak QEMU-specific warning, language-standard, optimization, or
    # linker policy into JACK. The dependency owns those choices independently.
    for key in ("CFLAGS", "CPPFLAGS", "CXXFLAGS", "LDFLAGS"):
        env.pop(key, None)
    env["CC"] = cc
    env["CXX"] = cxx

    # Keep the selected Darwin ABI coherent with QEMU without inheriting its
    # unrelated warning, optimization, language-standard, or linker flags.
    # A non-Apple Clang does not reliably infer the active macOS SDK, so make
    # the SDK and deployment target explicit. Otherwise Waf can misdiagnose
    # SDK headers such as <sys/types.h> as missing.
    if platform.system() == "Darwin":
        darwin_flags = shlex.join([
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ])
        env["CFLAGS"] = darwin_flags
        env["CXXFLAGS"] = darwin_flags
        env["LDFLAGS"] = darwin_flags
        env["SDKROOT"] = sdkroot
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment

    command = [
        sys.executable,
        "waf",
        "configure",
        f"--prefix={prefix}",
        f"--pkgconfigdir={prefix / 'lib' / 'pkgconfig'}",
        "--client-only",
        "--autostart=none",
        "--doxygen=no",
        "--tests=no",
        "--celt=no",
        "--samplerate=no",
        "--alsa=no",
        "--firewire=no",
        "--iio=no",
        "--portaudio=no",
        "--winmme=no",
        "--opus=no",
        "--systemd=no",
        "--db=no",
    ]

    print(f"WHP JACK bootstrap: {revision} -> {prefix}", file=sys.stderr)
    run_logged(command, cwd=SUBMODULE_DIR, env=env)
    run_logged([sys.executable, "waf", "build"], cwd=SUBMODULE_DIR, env=env)
    run_logged([sys.executable, "waf", "install"], cwd=SUBMODULE_DIR, env=env)

    if find_pkgconfig_file(prefix) is None:
        raise RuntimeError(f"JACK bootstrap did not install jack.pc under {prefix}")
    if not (prefix / "include" / "jack" / "jack.h").is_file():
        raise RuntimeError(f"JACK bootstrap did not install jack/jack.h under {prefix}")

    (prefix / ".whp-jack-bootstrap").write_text(marker, encoding="utf-8")
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    if args.mode == "auto" and system_jack_usable():
        print("WHP JACK bootstrap: host JACK is usable", file=sys.stderr)
        return 0

    try:
        prefix = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.mode == "auto":
            print(f"warning: optional WHP JACK bootstrap skipped: {exc}", file=sys.stderr)
            return 0
        print(f"error: WHP JACK bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
