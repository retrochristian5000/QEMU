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
SUBMODULE_REL = pathlib.Path("toolchains/zlib")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
ZLIB_BOOTSTRAP_SCHEMA = "1"
PKG_NAME = "zlib"


def run_text(command: List[str], *, cwd: pathlib.Path | None = None,
             env: dict[str, str] | None = None) -> str:
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


def run_logged(command: List[str], *, cwd: pathlib.Path | None = None,
               env: dict[str, str] | None = None) -> None:
    completed = subprocess.run(
        command, cwd=cwd, env=env, stdout=sys.stderr, stderr=sys.stderr,
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
        SUBMODULE_DIR / "configure",
        SUBMODULE_DIR / "zlib.h",
        SUBMODULE_DIR / "zlib.pc.in",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled zlib source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/zlib or use a Git checkout"
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


def ensure_zlib_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    expected_line = run_text(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)]
    )
    fields = expected_line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"zlib gitlink is not registered in QEMU: {SUBMODULE_REL}"
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
            "bundled zlib checkout does not match the QEMU gitlink: "
            f"{current_revision} != {expected_revision}"
        )

    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        raise RuntimeError(
            "bundled zlib submodule has tracked changes; commit them in the "
            "ZLIB fork and update the QEMU gitlink"
        )
    return expected_revision


def select_c_compiler() -> str:
    for env_name in ("CC", "CC_FOR_BUILD"):
        requested = os.environ.get(env_name, "")
        if not requested:
            continue
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"{env_name} is not executable: {candidate}")

    adapter = ROOT / "cc.sh"
    if adapter.is_file() and os.access(adapter, os.X_OK):
        completed = subprocess.run(
            [str(adapter), "--print-cc"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and candidate:
            return candidate
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU cc.sh could not resolve the zlib bootstrap compiler"
            + (f": {detail}" if detail else "")
        )

    for candidate in ("cc", "clang", "gcc"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("a native host C compiler is required to bootstrap zlib")


def select_make() -> str:
    requested = os.environ.get("MAKE_CMD") or os.environ.get("MAKE", "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("MAKE_CMD/MAKE must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if path and pathlib.Path(path).exists():
            return str(path)
        raise RuntimeError(f"MAKE_CMD/MAKE is not executable: {candidate}")
    for candidate in ("gmake", "make"):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError("make is required to bootstrap bundled zlib")


def compiler_version(cc: str) -> str:
    output = run_text([cc, "--version"])
    return output.splitlines()[0] if output else ""


def make_version(make: str) -> str:
    output = run_text([make, "--version"])
    return output.splitlines()[0] if output else make


def macos_settings() -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

    sdkroot = os.environ.get("SDKROOT", "")
    if not sdkroot:
        xcrun = shutil.which("xcrun")
        if not xcrun:
            raise RuntimeError("xcrun is required to locate the macOS SDK for zlib")
        sdkroot = run_text([xcrun, "--sdk", "macosx", "--show-sdk-path"])

    arch = os.environ.get("WHP_MACOS_ARCH", "auto").strip()
    if arch == "auto":
        machine = platform.machine().lower()
        if machine in ("arm64", "aarch64"):
            arch = "arm64"
        elif machine in ("x86_64", "amd64"):
            arch = "x86_64"
        else:
            raise RuntimeError(f"unsupported macOS architecture for zlib: {machine}")
    if arch not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(
            "WHP_MACOS_ARCH must be auto, arm64, arm64e, or x86_64: "
            f"{arch}"
        )

    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        pieces = version.split(".")
        deployment = ".".join(pieces[:2]) if version else "11.0"
    return sdkroot, arch, deployment


def incremental_build_enabled() -> bool:
    value = os.environ.get("WHP_INCREMENTAL_BUILD", "1").strip().lower()
    if value in ("1", "y", "yes", "true", "on"):
        return True
    if value in ("0", "n", "no", "false", "off"):
        return False
    raise RuntimeError(
        "WHP_INCREMENTAL_BUILD must be 0 or 1 "
        f"(boolean aliases are accepted): {value}"
    )


def zlib_cflags(sdkroot: str, arch: str, deployment: str) -> list[str]:
    flags = ["-O3"]
    if sdkroot:
        flags += [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
    return flags


def pkg_config() -> str | None:
    return shutil.which("pkg-config") or shutil.which("pkgconf")


def system_zlib_usable(cc: str) -> bool:
    pkgconf = pkg_config()
    if not pkgconf:
        return False
    if subprocess.run(
        [pkgconf, "--exists", PKG_NAME],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
    ).returncode != 0:
        return False

    flags = shlex.split(run_text([pkgconf, "--cflags", "--libs", PKG_NAME]))
    sdkroot, arch, deployment = macos_settings()
    with tempfile.TemporaryDirectory(prefix="whp-zlib-probe-") as tmp:
        root = pathlib.Path(tmp)
        source = root / "probe.c"
        binary = root / "probe"
        source.write_text(
            "#include <zlib.h>\n"
            "int main(void) { return zlibVersion() ? 0 : 1; }\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [cc, *zlib_cflags(sdkroot, arch, deployment), str(source),
             *flags, "-o", str(binary)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False,
        )
        return completed.returncode == 0


def find_pkgconfig_file(prefix: pathlib.Path) -> pathlib.Path | None:
    for candidate in (
        prefix / "lib" / "pkgconfig" / "zlib.pc",
        prefix / "lib64" / "pkgconfig" / "zlib.pc",
        prefix / "libdata" / "pkgconfig" / "zlib.pc",
    ):
        if candidate.is_file():
            return candidate
    return None


def workspace_marker_text(cc: str, cc_id: str, make: str, make_id: str,
                          shell: str, sdkroot: str, arch: str,
                          deployment: str, cflags: str) -> str:
    return (
        f"ZLIB_BOOTSTRAP_SCHEMA={ZLIB_BOOTSTRAP_SCHEMA}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"CC={cc}\n"
        f"CC_VERSION={cc_id}\n"
        f"MAKE={make}\n"
        f"MAKE_VERSION={make_id}\n"
        f"CONFIG_SHELL={shell}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
        f"CFLAGS={cflags}\n"
        "SHARED=0\n"
        "STATIC=1\n"
    )


def marker_text(revision: str, workspace_marker: str) -> str:
    return workspace_marker + f"ZLIB_GIT_COMMIT={revision}\n"


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-zlib-bootstrap"
    return (
        marker_file.is_file()
        and marker_file.read_text(encoding="utf-8", errors="replace") == marker
        and find_pkgconfig_file(prefix) is not None
        and (prefix / "include" / "zlib.h").is_file()
        and (prefix / "include" / "zconf.h").is_file()
        and (prefix / "lib" / "libz.a").is_file()
    )


def prepare_workspace(work_dir: pathlib.Path, prefix: pathlib.Path,
                      workspace_marker: str, *, incremental: bool) -> bool:
    marker_file = work_dir / ".whp-zlib-workspace"
    reuse = False
    if incremental and marker_file.is_file():
        reuse = (
            marker_file.read_text(encoding="utf-8", errors="replace")
            == workspace_marker
        )
    if reuse:
        return True

    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    return False


def bootstrap(build_root: pathlib.Path, cc: str) -> pathlib.Path:
    revision = ensure_zlib_source()
    make = select_make()
    shell = os.environ.get("CONFIG_SHELL", "") or shutil.which("sh")
    if not shell:
        raise RuntimeError("a POSIX shell is required to configure zlib")
    shell_argv = shlex.split(shell)
    if len(shell_argv) != 1:
        raise RuntimeError("CONFIG_SHELL must name exactly one executable")
    shell = shell_argv[0]

    sdkroot, arch, deployment = macos_settings()
    cflags = " ".join(zlib_cflags(sdkroot, arch, deployment))
    incremental = incremental_build_enabled()
    work_dir = build_root / "bootstrap" / "zlib"
    prefix = build_root / "deps" / "zlib"
    workspace_marker = workspace_marker_text(
        cc, compiler_version(cc), make, make_version(make), shell,
        sdkroot, arch, deployment, cflags,
    )
    marker = marker_text(revision, workspace_marker)
    if incremental and cache_valid(prefix, marker):
        return prefix

    reused = prepare_workspace(
        work_dir, prefix, workspace_marker, incremental=incremental
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in (
        "CFLAGS", "CPPFLAGS", "CXXFLAGS", "OBJCFLAGS", "OBJCXXFLAGS",
        "LDFLAGS", "LIBS", "CHOST",
    ):
        env.pop(key, None)
    env["CC"] = cc
    env["CFLAGS"] = cflags
    env["LDFLAGS"] = ""
    if sdkroot:
        env["SDKROOT"] = sdkroot
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment

    if reused:
        print(
            f"WHP zlib incremental rebuild: {revision} -> {prefix}",
            file=sys.stderr,
        )
    else:
        print(f"WHP zlib bootstrap: {revision} -> {prefix}", file=sys.stderr)

    run_logged(
        [shell, str(SUBMODULE_DIR / "configure"), "--static",
         f"--prefix={prefix}"],
        cwd=work_dir, env=env,
    )
    jobs = max(1, int(os.environ.get("JOBS", os.cpu_count() or 1)))
    run_logged([make, "-j", str(jobs)], cwd=work_dir, env=env)
    run_logged([make, "install"], cwd=work_dir, env=env)

    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        raise RuntimeError(f"zlib bootstrap did not install zlib.pc under {prefix}")
    if not (prefix / "lib" / "libz.a").is_file():
        raise RuntimeError(f"zlib bootstrap did not install libz.a under {prefix}")
    if not (prefix / "include" / "zlib.h").is_file():
        raise RuntimeError(f"zlib bootstrap did not install zlib.h under {prefix}")
    shared = list((prefix / "lib").glob("libz*.dylib"))
    shared += list((prefix / "lib").glob("libz*.so*"))
    if shared:
        raise RuntimeError(
            "static zlib bootstrap unexpectedly installed shared libraries: "
            + ", ".join(str(path) for path in shared)
        )

    (work_dir / ".whp-zlib-workspace").write_text(
        workspace_marker, encoding="utf-8"
    )
    (prefix / ".whp-zlib-bootstrap").write_text(marker, encoding="utf-8")
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    try:
        cc = select_c_compiler()
        if args.mode == "auto" and system_zlib_usable(cc):
            print("WHP zlib bootstrap: host zlib is usable", file=sys.stderr)
            return 0
        prefix = bootstrap(
            pathlib.Path(args.build_dir).expanduser().resolve(), cc
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.mode == "auto":
            print(
                f"warning: optional WHP zlib bootstrap skipped: {exc}",
                file=sys.stderr,
            )
            return 0
        print(f"error: WHP zlib bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
