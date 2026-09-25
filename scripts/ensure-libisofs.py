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
LIBISOFS_BOOTSTRAP_SCHEMA = "5"
LIBISOFS_MIN_VERSION = (1, 1, 2)
PKG_NAME = "libisofs-1"
LIBISOFS_CONFIGURE_ARGS = (
    "--disable-shared",
    "--enable-static",
    "--disable-libacl",
    "--disable-libjte",
    "--disable-ldconfig-at-install",
)


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

    names = ("gmake", "make") if name == "make" else (name,)
    for candidate in names:
        path = shutil.which(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap bundled libisofs")


def select_gnu_libtool(env_name: str, names: tuple[str, ...]) -> str:
    requested = os.environ.get(env_name, "")
    candidates: list[str] = []

    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if not path or not pathlib.Path(path).exists():
            raise RuntimeError(f"{env_name} is not executable: {candidate}")
        candidates.append(str(path))
    else:
        for name in names:
            path = shutil.which(name)
            if path and path not in candidates:
                candidates.append(path)

    for path in candidates:
        try:
            version = run_text([path, "--version"])
        except RuntimeError:
            continue
        if "GNU libtool" in version:
            return path
        if requested:
            raise RuntimeError(
                f"{env_name} must select GNU Libtool, not: {path}"
            )

    joined = "/".join(names)
    raise RuntimeError(
        f"GNU Libtool is required to bootstrap bundled libisofs "
        f"({joined} not found)"
    )


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
    raise RuntimeError("a usable configuration shell is required to bootstrap libisofs")


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


def pkg_config_flags(
    pkgconf: str,
    *,
    static: bool,
    env: dict[str, str] | None = None,
) -> list[str]:
    command = [pkgconf]
    if static:
        command.append("--static")
    command += ["--cflags", "--libs", PKG_NAME]
    return shlex.split(run_text(command, env=env))


def libisofs_link_probe(
    cc: str,
    pkgconf: str,
    *,
    static: bool,
    compile_flags: list[str] | None = None,
    link_flags: list[str] | None = None,
    env: dict[str, str] | None = None,
) -> bool:
    if subprocess.run(
        [pkgconf, "--atleast-version=1.1.2", PKG_NAME],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    ).returncode != 0:
        return False

    try:
        flags = pkg_config_flags(pkgconf, static=static, env=env)
    except RuntimeError:
        return False

    source = """#include <sys/types.h>
#include <time.h>
#include <libisofs.h>
int main(int argc, char **argv)
{
    (void) argv;
    if (iso_init() < 0)
        return 1;

    /*
     * Keep static-only translation units in the link without executing them.
     * All referenced APIs predate the declared libisofs >= 1.1.2 minimum.
     * zisofs/gzip pull zlib users; iso_set_local_charset pulls util.c, whose
     * translation unit contains libisofs' iconv users.
     */
    if (argc == 12345) {
        iso_file_add_zisofs_filter((IsoFile *) 0, 0);
        iso_file_add_gzip_filter((IsoFile *) 0, 0);
        iso_set_local_charset((char *) "UTF-8", 0);
    }

    iso_finish();
    return 0;
}
"""
    with tempfile.TemporaryDirectory(prefix="qemu-libisofs-probe-") as tmp:
        probe = pathlib.Path(tmp) / "probe.c"
        binary = pathlib.Path(tmp) / "probe"
        completed = subprocess.run(
            [
                cc,
                "-std=gnu11",
                "-Werror=strict-prototypes",
                *(compile_flags or []),
                str(probe),
                *(link_flags or []),
                *flags,
                "-o",
                str(binary),
            ],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if completed.returncode != 0:
            return False
        completed = subprocess.run(
            [str(binary)],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        return completed.returncode == 0


def strict_header_probe(cc: str, pkgconf: str) -> bool:
    return libisofs_link_probe(cc, pkgconf, static=False)


def system_libisofs_usable(cc: str) -> bool:
    pkgconf = pkg_config()
    if not pkgconf:
        return False
    sdkroot, arch, deployment = macos_settings()
    architecture_flags = (
        [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
        if sdkroot else []
    )
    return libisofs_link_probe(
        cc,
        pkgconf,
        static=False,
        compile_flags=architecture_flags,
        link_flags=architecture_flags,
    )


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


def find_static_library(prefix: pathlib.Path) -> pathlib.Path | None:
    for candidate in (
        prefix / "lib" / "libisofs.a",
        prefix / "lib64" / "libisofs.a",
    ):
        if candidate.is_file():
            return candidate
    for candidate in prefix.glob("**/libisofs.a"):
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


def workspace_marker_text(
    cc: str,
    cc_id: str,
    sdkroot: str,
    arch: str,
    deployment: str,
    config_shell: str,
    libtoolize: str,
    libtoolize_id: str,
    cflags: str,
    ldflags: str,
) -> str:
    return (
        f"LIBISOFS_BOOTSTRAP_SCHEMA={LIBISOFS_BOOTSTRAP_SCHEMA}\n"
        f"CC={cc}\n"
        f"CC_VERSION={cc_id}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
        f"CONFIG_SHELL={shell_identity(config_shell)}\n"
        f"LIBTOOLIZE={libtoolize}\n"
        f"LIBTOOLIZE_VERSION={libtoolize_id}\n"
        f"CFLAGS={cflags}\n"
        f"LDFLAGS={ldflags}\n"
        f"CONFIGURE_ARGS={shlex.join(LIBISOFS_CONFIGURE_ARGS)}\n"
        "STRICT_PROTOTYPES=1\n"
        "SHARED=0\n"
        "STATIC=1\n"
    )


def marker_text(revision: str, workspace_marker: str) -> str:
    return workspace_marker + f"LIBISOFS_GIT_COMMIT={revision}\n"


def prepare_workspace(
    work_dir: pathlib.Path,
    prefix: pathlib.Path,
    source_copy: pathlib.Path,
    workspace_marker: str,
    *,
    incremental: bool,
) -> bool:
    marker_file = work_dir / ".whp-libisofs-workspace"
    reuse = False
    if incremental and marker_file.is_file():
        try:
            reuse = (
                marker_file.read_text(encoding="utf-8", errors="replace")
                == workspace_marker
            )
        except OSError:
            reuse = False

    if reuse:
        # Refresh only the copied source. Keep the configured object tree and
        # installed prefix so Make can rebuild just what the new source needs.
        shutil.rmtree(source_copy, ignore_errors=True)
        return True

    # A changed compiler/SDK/architecture/Libtool/configure profile cannot
    # safely share objects. WHP_INCREMENTAL_BUILD=0 also deliberately lands
    # here even when the workspace marker is otherwise compatible.
    shutil.rmtree(work_dir, ignore_errors=True)
    shutil.rmtree(prefix, ignore_errors=True)
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    return False


def cache_valid(prefix: pathlib.Path, marker: str) -> bool:
    marker_file = prefix / ".whp-libisofs-bootstrap"
    if not marker_file.is_file():
        return False
    if marker_file.read_text(encoding="utf-8", errors="replace") != marker:
        return False
    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None or find_static_library(prefix) is None:
        return False
    return version_tuple(installed_version(pc_file)) >= LIBISOFS_MIN_VERSION


def bootstrap(build_root: pathlib.Path, cc: str) -> pathlib.Path:
    revision = ensure_libisofs_source()
    make = command_path("make", "MAKE")
    libtoolize = select_gnu_libtool(
        "LIBTOOLIZE", ("glibtoolize", "libtoolize")
    )
    config_shell = select_config_shell()
    sdkroot, arch, deployment = macos_settings()
    cc_id = compiler_version(cc)
    libtoolize_id = run_text([libtoolize, "--version"]).splitlines()[0]
    incremental = incremental_build_enabled()

    work_dir = build_root / "bootstrap" / "libisofs"
    source_copy = work_dir / "source"
    object_dir = work_dir / "build"
    prefix = build_root / "deps" / "libisofs"

    env = os.environ.copy()
    # INSTALL and LIBTOOL are project-generated Autotools variables. Do not
    # let caller state replace AC_PROG_INSTALL or the configured ./libtool.
    # The old LIBTOOL override could discard Darwin/arm64e settings captured
    # by configure and produced commands such as "libtool --mode=install 1".
    env.pop("INSTALL", None)
    env.pop("LIBTOOL", None)
    env["CC"] = cc
    env["LIBTOOLIZE"] = libtoolize
    env["CONFIG_SHELL"] = config_shell
    env["SHELL"] = config_shell
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

    workspace_marker = workspace_marker_text(
        cc,
        cc_id,
        sdkroot,
        arch,
        deployment,
        config_shell,
        libtoolize,
        libtoolize_id,
        env["CFLAGS"],
        env["LDFLAGS"],
    )
    marker = marker_text(revision, workspace_marker)
    if incremental and cache_valid(prefix, marker):
        return prefix

    reused_workspace = prepare_workspace(
        work_dir,
        prefix,
        source_copy,
        workspace_marker,
        incremental=incremental,
    )
    work_dir.mkdir(parents=True, exist_ok=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(
        SUBMODULE_DIR,
        source_copy,
        ignore=shutil.ignore_patterns(".git"),
    )

    if reused_workspace:
        print(
            f"WHP libisofs incremental rebuild: {revision} -> {prefix}",
            file=sys.stderr,
        )
    else:
        print(
            f"WHP libisofs bootstrap: {revision} -> {prefix}",
            file=sys.stderr,
        )

    run_logged([config_shell, "bootstrap"], cwd=source_copy, env=env)

    object_dir.mkdir(parents=True, exist_ok=True)
    configure = source_copy / "configure"
    run_logged(
        [
            config_shell,
            str(configure),
            f"--prefix={prefix}",
            *LIBISOFS_CONFIGURE_ARGS,
        ],
        cwd=object_dir,
        env=env,
    )
    local_libtool = object_dir / "libtool"
    if not local_libtool.is_file():
        raise RuntimeError(
            "libisofs configure did not generate its project-local libtool"
        )
    run_logged(
        [make, "-j", str(max(1, os.cpu_count() or 1))],
        cwd=object_dir,
        env=env,
    )
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
    if not pkgconf:
        raise RuntimeError(
            "pkg-config/pkgconf is required to validate bootstrapped libisofs"
        )
    probe_env = os.environ.copy()
    pc_dir = str(pc_file.parent)
    probe_env["PKG_CONFIG_PATH"] = (
        pc_dir
        + (":" + probe_env["PKG_CONFIG_PATH"]
           if probe_env.get("PKG_CONFIG_PATH") else "")
    )
    static_flags = pkg_config_flags(pkgconf, static=True, env=probe_env)
    if "-lz" not in static_flags:
        raise RuntimeError(
            "bootstrapped static libisofs does not export its zlib dependency"
        )
    if "-lpthread" not in static_flags:
        raise RuntimeError(
            "bootstrapped static libisofs does not export its pthread dependency"
        )
    architecture_flags = (
        [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
        if sdkroot else []
    )
    if not libisofs_link_probe(
        cc,
        pkgconf,
        static=True,
        compile_flags=architecture_flags,
        link_flags=architecture_flags,
        env=probe_env,
    ):
        raise RuntimeError(
            "bootstrapped libisofs failed the static compile/link/runtime probe"
        )

    # Publish reuse state only after install and validation have succeeded.
    # A failed build therefore cannot bless a new ABI/configuration identity.
    (work_dir / ".whp-libisofs-workspace").write_text(
        workspace_marker, encoding="utf-8"
    )
    (prefix / ".whp-libisofs-bootstrap").write_text(marker, encoding="utf-8")
    return prefix

def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force"), default="auto")
    args = parser.parse_args(argv)

    if platform.system() != "Darwin":
        if args.mode == "force":
            print(
                "error: WHP libisofs bootstrap is supported only on Darwin",
                file=sys.stderr,
            )
            return 1
        print(
            "WHP libisofs bootstrap: skipped on non-Darwin host",
            file=sys.stderr,
        )
        return 0

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
