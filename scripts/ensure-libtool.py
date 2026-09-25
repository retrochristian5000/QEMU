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
SUBMODULE_REL = pathlib.Path("toolchains/libtool")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
NESTED_SUBMODULES = (
    pathlib.Path("gnulib"),
    pathlib.Path("gl-mod/bootstrap"),
)
LIBTOOL_BOOTSTRAP_SCHEMA = "2"


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


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def gitlink_revision(repo_dir: pathlib.Path, relpath: pathlib.Path) -> str:
    line = run_text(
        ["git", "-C", str(repo_dir), "ls-tree", "HEAD", "--", str(relpath)]
    )
    fields = line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"gitlink is not registered in {repo_dir}: {relpath}"
        )
    return fields[2]


def ensure_nested_submodules() -> dict[pathlib.Path, str]:
    expected: dict[pathlib.Path, str] = {}
    for relpath in NESTED_SUBMODULES:
        expected[relpath] = gitlink_revision(SUBMODULE_DIR, relpath)

    run_logged(
        [
            "git", "-C", str(SUBMODULE_DIR), "submodule", "sync", "--",
            *[str(path) for path in NESTED_SUBMODULES],
        ]
    )
    run_logged(
        [
            "git", "-C", str(SUBMODULE_DIR), "submodule", "update", "--init",
            "--depth", "1", "--",
            *[str(path) for path in NESTED_SUBMODULES],
        ]
    )

    for relpath, revision in expected.items():
        nested = SUBMODULE_DIR / relpath
        current = run_text(["git", "-C", str(nested), "rev-parse", "HEAD"])
        if current != revision:
            raise RuntimeError(
                f"nested Libtool submodule does not match gitlink: "
                f"{relpath}: {current} != {revision}"
            )
        dirty = run_text(
            [
                "git", "-C", str(nested), "status", "--porcelain",
                "--untracked-files=no",
            ]
        )
        if dirty:
            raise RuntimeError(
                f"nested Libtool submodule has tracked changes: {relpath}"
            )
    return expected


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "bootstrap",
        SUBMODULE_DIR / "configure.ac",
        SUBMODULE_DIR / "libtoolize.in",
        SUBMODULE_DIR / "build-aux" / "ltmain.in",
    )
    if not candidates[0].is_file():
        raise RuntimeError(
            f"bundled Libtool source is unavailable: {SUBMODULE_DIR}; "
            "initialize toolchains/libtool or use a Git checkout"
        )
    for relpath in NESTED_SUBMODULES:
        if not (SUBMODULE_DIR / relpath).is_dir():
            raise RuntimeError(
                f"bundled Libtool nested source is unavailable: "
                f"{SUBMODULE_DIR / relpath}"
            )

    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return f"archive-{digest.hexdigest()}"


def ensure_libtool_source() -> tuple[str, dict[pathlib.Path, str]]:
    if not git_checkout_available():
        return archive_source_signature(), {}

    expected = gitlink_revision(ROOT, SUBMODULE_REL)
    current = ""
    if (SUBMODULE_DIR / ".git").exists():
        try:
            current = run_text(
                ["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"]
            )
        except RuntimeError:
            current = ""

    if current != expected:
        run_logged(
            [
                "git", "-C", str(ROOT), "submodule", "update", "--init",
                "--depth", "1", str(SUBMODULE_REL),
            ]
        )
        current = run_text(
            ["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"]
        )
    if current != expected:
        raise RuntimeError(
            "bundled Libtool checkout does not match the QEMU gitlink: "
            f"{current} != {expected}"
        )

    nested = ensure_nested_submodules()
    dirty = run_text(
        [
            "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
            "--untracked-files=no",
        ]
    )
    if dirty:
        raise RuntimeError(
            "bundled Libtool submodule has tracked changes; commit them in "
            "the Libtool fork and update the QEMU gitlink"
        )
    return expected, nested


def extract_git_archive(
    repo_dir: pathlib.Path, revision: str, destination: pathlib.Path
) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo_dir), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode(
            "utf-8", errors="replace"
        ).strip()
        raise RuntimeError(
            f"could not archive pinned source {revision}"
            + (f": {detail}" if detail else "")
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        archive.extractall(destination)


def copy_libtool_source(
    revision: str,
    nested_revisions: dict[pathlib.Path, str],
    destination: pathlib.Path,
    config_shell: str,
) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    if git_checkout_available() and (SUBMODULE_DIR / ".git").exists():
        extract_git_archive(SUBMODULE_DIR, revision, destination)
        for relpath, nested_revision in nested_revisions.items():
            extract_git_archive(
                SUBMODULE_DIR / relpath,
                nested_revision,
                destination / relpath,
            )

        version_helper = (
            SUBMODULE_DIR / "gnulib" / "build-aux" / "git-version-gen"
        )
        if not version_helper.is_file():
            raise RuntimeError(
                f"pinned gnulib git-version-gen is unavailable: {version_helper}"
            )
        version = run_text(
            [config_shell, str(version_helper), ".tarball-version"],
            cwd=SUBMODULE_DIR,
        )
        (destination / ".tarball-version").write_text(
            version + "\n", encoding="utf-8"
        )
        return

    shutil.copytree(
        SUBMODULE_DIR,
        destination,
        ignore=shutil.ignore_patterns(".git"),
    )


def command_path(
    name: str,
    env_name: str | None = None,
    aliases: tuple[str, ...] = (),
) -> str:
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

    for candidate in (name, *aliases):
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap bundled Libtool")


def gnu_libtool_version(path: str) -> str:
    output = run_text([path, "--version"])
    if "GNU libtool" not in output:
        raise RuntimeError(f"not GNU Libtool: {path}")
    return output.splitlines()[0] if output else ""


def select_gnu_make() -> str:
    requested = os.environ.get("MAKE") or os.environ.get("MAKE_CMD", "")
    candidates: list[str] = []
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("MAKE/MAKE_CMD must name exactly one executable")
        candidate = argv[0]
        path = (
            candidate
            if pathlib.Path(candidate).is_absolute()
            else shutil.which(candidate)
        )
        if not path or not pathlib.Path(path).exists():
            raise RuntimeError(f"MAKE/MAKE_CMD is not executable: {candidate}")
        candidates.append(str(path))
    else:
        for name in ("gmake", "make"):
            path = shutil.which(name)
            if path and path not in candidates:
                candidates.append(path)

    for path in candidates:
        try:
            output = run_text([path, "--version"])
        except RuntimeError:
            continue
        if "GNU Make" in output:
            return path
    raise RuntimeError("GNU Make is required to bootstrap bundled Libtool")


def system_libtool_pair() -> tuple[str, str] | None:
    requested_tool = os.environ.get("LIBTOOL", "")
    requested_toolize = os.environ.get("LIBTOOLIZE", "")

    def resolve(
        requested: str, names: tuple[str, ...], env_name: str
    ) -> str | None:
        if requested:
            argv = shlex.split(requested)
            if len(argv) != 1:
                raise RuntimeError(
                    f"{env_name} must name exactly one executable"
                )
            candidate = argv[0]
            path = (
                candidate
                if pathlib.Path(candidate).is_absolute()
                else shutil.which(candidate)
            )
            if not path or not pathlib.Path(path).exists():
                raise RuntimeError(f"{env_name} is not executable: {candidate}")
            return str(path)
        for name in names:
            path = shutil.which(name)
            if path:
                try:
                    gnu_libtool_version(path)
                except RuntimeError:
                    continue
                return path
        return None

    tool = resolve(
        requested_tool,
        ("glibtool", "libtool") if platform.system() == "Darwin"
        else ("libtool", "glibtool"),
        "LIBTOOL",
    )
    toolize = resolve(
        requested_toolize,
        ("glibtoolize", "libtoolize") if platform.system() == "Darwin"
        else ("libtoolize", "glibtoolize"),
        "LIBTOOLIZE",
    )

    if requested_tool and tool:
        gnu_libtool_version(tool)
    if requested_toolize and toolize:
        gnu_libtool_version(toolize)
    if tool and toolize:
        return tool, toolize
    if requested_tool or requested_toolize:
        raise RuntimeError(
            "LIBTOOL and LIBTOOLIZE must resolve to a complete GNU Libtool pair"
        )
    return None


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
    raise RuntimeError("a host C compiler is required to bootstrap Libtool")


def compiler_version(cc: str) -> str:
    output = run_text([cc, "--version"])
    return output.splitlines()[0] if output else ""


def shell_usable(path: str) -> bool:
    completed = subprocess.run(
        [path, "-c", "exit 0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def resolve_shell(requested: str, env_name: str) -> str:
    argv = shlex.split(requested)
    if len(argv) != 1:
        raise RuntimeError(f"{env_name} must name exactly one executable")
    candidate = argv[0]
    path = (
        candidate
        if pathlib.Path(candidate).is_absolute()
        else shutil.which(candidate)
    )
    if not path or not pathlib.Path(path).exists() or not shell_usable(str(path)):
        raise RuntimeError(f"{env_name} is not a usable shell: {candidate}")
    return str(path)


def select_config_shell() -> str:
    for env_name in ("WHP_BUILD_BASH", "CONFIG_SHELL"):
        requested = os.environ.get(env_name, "")
        if requested:
            return resolve_shell(requested, env_name)

    for name in ("bash", "sh"):
        path = shutil.which(name)
        if path and shell_usable(path):
            return path
    raise RuntimeError("a usable configuration shell is required to bootstrap Libtool")


def shell_identity(path: str) -> str:
    completed = subprocess.run(
        [path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    first = completed.stdout.splitlines()[0] if completed.stdout else ""
    return f"{path}|{first}"


def macos_settings() -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

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
        raise RuntimeError(f"unsupported WHP_MACOS_ARCH for Libtool: {arch}")

    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        pieces = version.split(".")
        deployment = ".".join(pieces[:2]) if version else "11.0"
    return sdkroot, arch, deployment


def tool_identity(path: str) -> str:
    output = run_text([path, "--version"])
    first = output.splitlines()[0] if output else ""
    return f"{path}|{first}"


def marker_text(
    revision: str,
    nested_revisions: dict[pathlib.Path, str],
    cc: str,
    sdkroot: str,
    arch: str,
    deployment: str,
    config_shell: str,
    tools: dict[str, str],
) -> str:
    nested = ",".join(
        f"{path}={nested_revisions[path]}"
        for path in sorted(nested_revisions, key=str)
    )
    lines = [
        f"LIBTOOL_BOOTSTRAP_SCHEMA={LIBTOOL_BOOTSTRAP_SCHEMA}",
        f"LIBTOOL_GIT_COMMIT={revision}",
        f"NESTED_GITLINKS={nested}",
        f"HOST_SYSTEM={platform.system()}",
        f"HOST_MACHINE={platform.machine()}",
        f"CC={cc}",
        f"CC_VERSION={compiler_version(cc)}",
        f"SDKROOT={sdkroot}",
        f"WHP_MACOS_ARCH={arch}",
        f"MACOSX_DEPLOYMENT_TARGET={deployment}",
        f"CONFIG_SHELL={shell_identity(config_shell)}",
        "LTDL_INSTALL=disabled",
    ]
    for name in sorted(tools):
        lines.append(f"{name}={tool_identity(tools[name])}")
    return "\n".join(lines) + "\n"


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-libtool-bootstrap"
    libtool = prefix / "bin" / "libtool"
    libtoolize = prefix / "bin" / "libtoolize"
    if not marker_file.is_file():
        return False
    if marker_file.read_text(encoding="utf-8", errors="replace") != marker:
        return False
    try:
        gnu_libtool_version(str(libtool))
        gnu_libtool_version(str(libtoolize))
    except (OSError, RuntimeError):
        return False
    return True


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision, nested_revisions = ensure_libtool_source()
    cc = select_c_compiler()
    sdkroot, arch, deployment = macos_settings()
    config_shell = select_config_shell()

    tools = {
        "MAKE": select_gnu_make(),
        "AUTOCONF": command_path("autoconf", "AUTOCONF"),
        "AUTOMAKE": command_path("automake", "AUTOMAKE"),
        "ACLOCAL": command_path("aclocal", "ACLOCAL"),
        "AUTOHEADER": command_path("autoheader", "AUTOHEADER"),
        "AUTOM4TE": command_path("autom4te", "AUTOM4TE"),
        "AUTORECONF": command_path("autoreconf", "AUTORECONF"),
        "HELP2MAN": command_path("help2man", "HELP2MAN"),
        "MAKEINFO": command_path("makeinfo", "MAKEINFO"),
        "XZ": command_path("xz", "XZ"),
        "M4": command_path("m4", "M4"),
        "PERL": command_path("perl", "PERL"),
    }

    prefix = build_root / "deps" / "libtool"
    work_dir = build_root / "bootstrap" / "libtool"
    source_copy = work_dir / "source"
    object_dir = work_dir / "build"
    marker = marker_text(
        revision,
        nested_revisions,
        cc,
        sdkroot,
        arch,
        deployment,
        config_shell,
        tools,
    )
    if cache_valid(prefix, marker):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work_dir, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    copy_libtool_source(
        revision, nested_revisions, source_copy, config_shell
    )
    object_dir.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in (
        "INSTALL", "LIBTOOL", "LIBTOOLIZE", "BASH_ENV", "ENV",
        "CFLAGS", "CPPFLAGS", "LDFLAGS",
    ):
        env.pop(key, None)
    env["CC"] = cc
    env["CONFIG_SHELL"] = config_shell
    env["SHELL"] = config_shell
    for name, path in tools.items():
        env[name] = path

    tool_dirs: list[str] = []
    for path in tools.values():
        parent = str(pathlib.Path(path).parent)
        if parent not in tool_dirs:
            tool_dirs.append(parent)
    env["PATH"] = os.pathsep.join(tool_dirs + [env.get("PATH", "")])

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

    print(
        f"WHP Libtool bootstrap: {revision} -> {prefix}",
        file=sys.stderr,
    )
    run_logged(
        [
            config_shell, str(source_copy / "bootstrap"),
            "--skip-po",
            "--no-git",
            "--copy",
            f"--gnulib-srcdir={source_copy / 'gnulib'}",
        ],
        cwd=source_copy,
        env=env,
    )
    configure = source_copy / "configure"
    if not configure.is_file():
        raise RuntimeError("Libtool bootstrap did not generate configure")

    run_logged(
        [
            config_shell, str(configure),
            f"--prefix={prefix}",
            "--disable-ltdl-install",
        ],
        cwd=object_dir,
        env=env,
    )
    jobs = str(max(1, os.cpu_count() or 1))
    run_logged([tools["MAKE"], "-j", jobs], cwd=object_dir, env=env)
    run_logged([tools["MAKE"], "install"], cwd=object_dir, env=env)

    libtool = prefix / "bin" / "libtool"
    libtoolize = prefix / "bin" / "libtoolize"
    gnu_libtool_version(str(libtool))
    gnu_libtool_version(str(libtoolize))
    (prefix / ".whp-libtool-bootstrap").write_text(
        marker, encoding="utf-8"
    )
    return prefix


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    requested_pair = bool(
        os.environ.get("LIBTOOL") or os.environ.get("LIBTOOLIZE")
    )
    try:
        if args.mode == "auto":
            pair = system_libtool_pair()
            if pair:
                print(
                    f"WHP Libtool bootstrap: using host GNU Libtool "
                    f"({pair[0]}, {pair[1]})",
                    file=sys.stderr,
                )
                return 0

        prefix = bootstrap(
            pathlib.Path(args.build_dir).expanduser().resolve()
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        if args.mode == "auto" and not requested_pair:
            print(
                f"warning: optional WHP Libtool bootstrap skipped: {exc}",
                file=sys.stderr,
            )
            return 0
        print(f"error: WHP Libtool bootstrap failed: {exc}", file=sys.stderr)
        return 1

    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
