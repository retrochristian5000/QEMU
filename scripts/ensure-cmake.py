#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build a native CMake from the pinned fork, without CMake or LLVM inputs."""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import clean_host_environment, reconcile_submodule, select_native_sdk

SUBMODULE = Path("toolchains/cmake")
SCHEMA = "1"
MINIMUM = (3, 20)


def admitted_tool(seed: str, option: str) -> str:
    adapter = ROOT / "seeds" / seed
    if not adapter.is_file():
        raise RuntimeError(f"native {seed} adapter is missing: {adapter}")
    # Several POSIX seed adapters are tracked without executable mode
    # (100644), including make.sh. Run their readable source via /bin/sh;
    # the selected compiler/Make binary still must be executable.
    result = subprocess.run(
        ["/bin/sh", str(adapter), option], capture_output=True,
        text=True, check=False,
    )
    path = result.stdout.strip()
    if (result.returncode or not path or "\n" in path
            or not Path(path).is_absolute() or not Path(path).is_file()
            or not os.access(path, os.X_OK)):
        raise RuntimeError(
            f"native {seed} did not select an executable: "
            f"{result.stderr.strip() or path or 'missing'}"
        )
    return path


def version(tool: str) -> str:
    result = subprocess.run(
        [tool, "--version"], capture_output=True, text=True, check=False,
    )
    if result.returncode or not result.stdout.strip():
        raise RuntimeError(f"native tool cannot report its version: {tool}")
    return result.stdout.splitlines()[0]


def usable(binary: Path) -> bool:
    if not binary.is_file() or not os.access(binary, os.X_OK):
        return False
    banner = subprocess.run(
        [str(binary), "--version"], capture_output=True, text=True,
        check=False,
    )
    match = (re.match(r"^cmake version ([0-9]+)\.([0-9]+)", banner.stdout)
             if banner.returncode == 0 else None)
    if not match or tuple(map(int, match.groups())) < MINIMUM:
        return False
    features = subprocess.run(
        [str(binary), "-E", "capabilities"], capture_output=True,
        text=True, check=False,
    )
    if features.returncode:
        return False
    try:
        return isinstance(json.loads(features.stdout).get("generators"), list)
    except (ValueError, AttributeError):
        return False


def identity(revision: str, cc: str, cxx: str, make: str,
             sdk: str, deployment: str) -> str:
    evidence = (SCHEMA, revision, platform.system(), platform.machine(),
                cc, version(cc), cxx, version(cxx), make, version(make),
                sdk, deployment)
    return hashlib.sha256(
        json.dumps(evidence).encode("utf-8")
    ).hexdigest()


def host_environment(cc: str, cxx: str, make: str,
                     sdk: str, deployment: str) -> dict[str, str]:
    env = clean_host_environment(os.environ)
    for name in (
        "CMAKE_TOOLCHAIN_FILE", "CMAKE_SYSROOT", "CMAKE_FIND_ROOT_PATH",
        "CMAKE_GENERATOR", "CMAKE_GENERATOR_PLATFORM", "CMAKE_GENERATOR_TOOLSET",
        "CMAKE_GENERATOR_INSTANCE", "CMAKE_PROJECT_TOP_LEVEL_INCLUDES",
        "CMAKE_PROJECT_INCLUDE", "CMAKE_PROJECT_INCLUDE_BEFORE",
        "CMAKE_C_COMPILER_TARGET", "CMAKE_CXX_COMPILER_TARGET",
        "CMAKE_OSX_ARCHITECTURES",
    ):
        env.pop(name, None)
    env.update({"CC": cc, "CXX": cxx, "MAKE": make,
                "CFLAGS": "", "CXXFLAGS": "", "LDFLAGS": ""})
    if platform.system() == "Darwin":
        env["SDKROOT"] = sdk
        if deployment:
            env["MACOSX_DEPLOYMENT_TARGET"] = deployment
        else:
            env.pop("MACOSX_DEPLOYMENT_TARGET", None)
    else:
        for name in ("SDKROOT", "DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET"):
            env.pop(name, None)
    return env


def verify_native_compiler_pair(
    cc: str, cxx: str, environment: dict[str, str], sdk: str
) -> None:
    """Prove the selected build-machine C/C++ objects can link and execute.

    CMake is a native build tool even when QEMU or LLVM later targets a guest.
    Report driver triples as diagnostics only: Darwin kernel versions and
    macOS deployment versions do not have interchangeable numeric meanings.
    """
    def target_hint(driver: str) -> str:
        try:
            result = subprocess.run(
                [driver, "-dumpmachine"], env=environment,
                capture_output=True, text=True, check=False, timeout=10,
            )
        except (OSError, subprocess.TimeoutExpired):
            return "unavailable"
        return result.stdout.strip().splitlines()[0] if (
            result.returncode == 0 and result.stdout.strip()
        ) else "unavailable"

    # Test the exact selected SDK, not an inherited target sysroot. Neither
    # compiler nor linker is allowed to receive guest --target/-arch flags.
    sdk_args = ["-isysroot", sdk] if sdk else []
    with tempfile.TemporaryDirectory(prefix="whp-cmake-host-abi-") as name:
        directory = Path(name)
        c_source = directory / "native.c"
        cxx_source = directory / "native.cc"
        c_object = directory / "native-c.o"
        cxx_object = directory / "native-cxx.o"
        executable = directory / "native-check"
        c_source.write_text(
            "int whp_cmake_native_c(int value) { return value + 2; }\n",
            encoding="utf-8",
        )
        cxx_source.write_text(
            'extern "C" int whp_cmake_native_c(int);\n'
            "int main() { return whp_cmake_native_c(40) == 42 ? 0 : 1; }\n",
            encoding="utf-8",
        )
        commands = (
            ("C compilation", [cc, *sdk_args, "-c", str(c_source),
                               "-o", str(c_object)]),
            ("C++ compilation", [cxx, *sdk_args, "-std=c++17", "-c",
                                 str(cxx_source), "-o", str(cxx_object)]),
            ("mixed C/C++ link", [cxx, *sdk_args, str(c_object),
                                   str(cxx_object), "-o", str(executable)]),
            ("native execution", [str(executable)]),
        )
        for stage, command in commands:
            try:
                result = subprocess.run(
                    command, env=environment, cwd=directory,
                    capture_output=True, text=True, check=False, timeout=30,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                detail = str(exc)
            else:
                if result.returncode == 0:
                    continue
                detail = (result.stderr.strip() or result.stdout.strip()
                          or f"exit {result.returncode}")
            raise RuntimeError(
                f"CMake build/host compiler pair failed {stage}: {detail} "
                f"(C={cc}, triple={target_hint(cc)}; "
                f"C++={cxx}, triple={target_hint(cxx)}). "
                "The C and C++ drivers must produce compatible native "
                "objects; target triples alone do not establish that."
            )


def build(build_dir: Path) -> Path:
    git = os.environ.get("WHP_GIT_SEED") or "git"
    revision = reconcile_submodule(ROOT, SUBMODULE, git=git)
    source = ROOT / SUBMODULE
    if not (source / "bootstrap").is_file():
        raise RuntimeError(f"missing pinned CMake bootstrap: {source}")
    dirty = subprocess.run(
        [git, "-C", str(source), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True, check=False,
    )
    if dirty.returncode or dirty.stdout.strip():
        raise RuntimeError("pinned CMake source is inaccessible or has tracked modifications")
    cc = admitted_tool("cc.sh", "--print-cc")
    cxx = admitted_tool("cxx.sh", "--print-cxx")
    make = admitted_tool("make.sh", "--print-make")
    sdk = select_native_sdk(ROOT) if platform.system() == "Darwin" else ""
    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "") if sdk else ""
    if deployment and not re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,2}", deployment):
        raise RuntimeError("invalid MACOSX_DEPLOYMENT_TARGET for host CMake")
    key = identity(revision, cc, cxx, make, sdk, deployment)
    home = build_dir.resolve() / ".whp-host-tools"
    home.mkdir(parents=True, exist_ok=True)
    lane = home / f"cmake-{revision[:12]}-{key[:16]}"
    binary = lane / "install/bin/cmake"
    marker = lane / ".whp-cmake-bootstrap"
    jobs = os.environ.get("JOBS", "2")
    if not jobs.isdecimal() or int(jobs) < 1:
        raise RuntimeError(f"invalid CMake bootstrap JOBS: {jobs!r}")
    environment = host_environment(cc, cxx, make, sdk, deployment)

    # Keep interrupted CMake builds incremental and avoid concurrent writers.
    with (home / ".whp-cmake.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if marker.is_file() and marker.read_text(encoding="utf-8") == key + "\n":
            if usable(binary):
                return binary
        # Validate the C/C++ ABI at the source-build boundary, after a
        # reusable native CMake installation has already been considered.
        verify_native_compiler_pair(cc, cxx, environment, sdk)
        work = lane / "work"
        work.mkdir(parents=True, exist_ok=True)
        commands = [
            ["/bin/sh", str(source / "bootstrap"),
             f"--prefix={lane / 'install'}", f"--parallel={jobs}",
             "--no-qt-gui", "--no-debugger", "--",
             "-DCMAKE_USE_OPENSSL=OFF", "-DBUILD_TESTING=OFF"],
            [make, "-j", jobs],
            [make, "install"],
        ]
        print(f"WHP CMake bootstrap: source={revision[:12]}, compiler={cxx}",
              file=sys.stderr)
        for command in commands:
            subprocess.run(command, cwd=work, env=environment,
                           stdout=sys.stderr, stderr=sys.stderr, check=True)
        if not usable(binary):
            raise RuntimeError(f"installed fork CMake is not usable: {binary}")
        marker.write_text(key + "\n", encoding="utf-8")
    return binary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", type=Path, default=ROOT / "build")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        binary = build(args.build_dir)
    except (OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: native CMake source bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(binary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
