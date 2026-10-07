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
LIBISOFS_BOOTSTRAP_SCHEMA = "17"
LIBISOFS_MIN_VERSION = (1, 1, 2)
PKG_NAME = "libisofs-1"
LIBISOFS_C_STANDARD = "gnu11"
LIBISOFS_CONFIGURE_ARGS = (
    "--disable-shared",
    "--enable-static",
    "--disable-demo",
    "--disable-docs",
    "--disable-versioned-libs",
    "--disable-libacl",
    "--disable-xattr",
    "--disable-lfa-flags",
    "--disable-projid",
    "--disable-dir-rec-size-check",
    "--disable-debug",
    "--disable-libjte",
    "--disable-ldconfig-at-install",
)
LIBISOFS_INSTALL_TARGETS = (
    "install-libLTLIBRARIES",
    # Use Automake's stable aggregate for headers and generated pkg-config
    # data. nodist_pkgconfig_DATA generates install-nodist_pkgconfigDATA, not
    # install-pkgconfigDATA, so calling the leaf name directly is incorrect.
    "install-data",
)
QEMU_UNUSED_SOURCE_DIRS = (
    "demo",
    "doc",
    "test",
    ".github",
    ".settings",
)
QEMU_UNUSED_SOURCE_FILES = (
    ".cproject",
    ".cdtproject",
    ".project",
    ".bzrignore",
    "README_AI",
    "SECURITY.md",
    "TODO",
    "ChangeLog",
    "Roadmap",
)

# These variables belong to Autoconf/Automake's generated utility layer.
# Inheriting them from QEMU's caller can replace locally detected install,
# directory-creation, or symlink commands with unrelated values. Keep
# compiler/binutils variables out of this list: those are intentional inputs.
AUTOTOOLS_UTILITY_ENV = (
    "INSTALL",
    "INSTALL_PROGRAM",
    "INSTALL_SCRIPT",
    "INSTALL_DATA",
    "INSTALL_STRIP_PROGRAM",
    "MKDIR_P",
    "mkdir_p",
    "LN_S",
)

DEPENDENCY_FLAG_ENV = (
    "CFLAGS",
    "CPPFLAGS",
    "CXXFLAGS",
    "OBJCFLAGS",
    "OBJCXXFLAGS",
    "LDFLAGS",
    "LIBS",
    "CPP",
    "LD",
    # Ambient dependency search roots can silently reintroduce Homebrew or
    # another caller's libraries even after CPPFLAGS/LDFLAGS are cleared.
    "CPATH",
    "C_INCLUDE_PATH",
    "CPLUS_INCLUDE_PATH",
    "OBJC_INCLUDE_PATH",
    "LIBRARY_PATH",
    "DYLD_LIBRARY_PATH",
    "DYLD_FALLBACK_LIBRARY_PATH",
    "PKG_CONFIG_PATH",
    "PKG_CONFIG_LIBDIR",
    "PKG_CONFIG_SYSROOT_DIR",
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


def select_gnu_make() -> str:
    requested = os.environ.get("MAKE_CMD") or os.environ.get("MAKE", "")
    candidates: list[str] = []

    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("MAKE_CMD/MAKE must name exactly one executable")
        candidate = argv[0]
        path = (
            candidate
            if pathlib.Path(candidate).is_absolute()
            else shutil.which(candidate)
        )
        if not path or not pathlib.Path(path).exists():
            raise RuntimeError(
                f"MAKE_CMD/MAKE is not executable: {candidate}"
            )
        candidates.append(str(path))
    else:
        for name in ("gmake", "make"):
            path = shutil.which(name)
            if path and path not in candidates:
                candidates.append(path)

    for path in candidates:
        try:
            version = run_text([path, "--version"])
        except RuntimeError:
            continue
        if version.startswith("GNU Make "):
            return path
        if requested:
            raise RuntimeError(
                f"MAKE_CMD/MAKE must select GNU Make, not: {path}"
            )

    raise RuntimeError("GNU Make is required to bootstrap bundled libisofs")


def semantic_sed_usable(path: str) -> bool:
    probes = (
        ("alpha\n", ["-n", "s/^alpha$/beta/p"], "beta\n"),
        ("A B/C\n", ["s,[^A-Za-z0-9_.-],-,g"], "A-B-C\n"),
        (
            "AR=/tmp/llvm-ar|LLVM\n",
            ["-n", r"s#^AR=\([^|]*\)|.*$#\1#p"],
            "/tmp/llvm-ar\n",
        ),
        ("one\ntwo\n", ["-n", "1p"], "one\n"),
    )
    for data, args, expected in probes:
        completed = subprocess.run(
            [path, *args],
            input=data,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if completed.returncode != 0 or completed.stdout != expected:
            return False
    return True


def select_sed() -> str:
    requested = os.environ.get("SED", "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("SED must name exactly one executable")
        candidate = argv[0]
        path = (
            candidate
            if pathlib.Path(candidate).is_absolute()
            else shutil.which(candidate)
        )
        if (
            not path
            or not pathlib.Path(path).is_file()
            or not os.access(path, os.X_OK)
            or not semantic_sed_usable(str(path))
        ):
            raise RuntimeError(f"SED is not a usable sed executable: {candidate}")
        return str(path)

    adapter = ROOT / "sed.sh"
    if not adapter.is_file() or not os.access(adapter, os.X_OK):
        raise RuntimeError(f"QEMU sed seed adapter is unavailable: {adapter}")
    completed = subprocess.run(
        [str(adapter), "--print-seed"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    path = completed.stdout.strip()
    if (
        completed.returncode != 0
        or not path
        or not pathlib.Path(path).is_file()
        or not os.access(path, os.X_OK)
        or not semantic_sed_usable(path)
    ):
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU sed.sh could not resolve a usable libisofs bootstrap sed"
            + (f": {detail}" if detail else "")
        )
    return path


def isolate_autotools_utility_env(env: dict[str, str]) -> None:
    for name in AUTOTOOLS_UTILITY_ENV:
        env.pop(name, None)


def isolate_dependency_flag_env(env: dict[str, str]) -> None:
    """Keep QEMU host/compiler policy out of the private libisofs build."""
    for name in DEPENDENCY_FLAG_ENV:
        env.pop(name, None)

def gnu_m4_version(path: str) -> str:
    completed = subprocess.run(
        [path, "--gnu", "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    if completed.returncode != 0 or "GNU M4" not in output:
        detail = output.splitlines()[0] if output else "<no version output>"
        raise RuntimeError(
            f"not GNU M4 with --gnu support: {path}: {detail}"
        )
    return output.splitlines()[0]


def select_gnu_m4() -> str:
    requested = os.environ.get("M4", "")
    candidates: list[str] = []

    def add_candidate(candidate: str | None) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("M4 must name exactly one executable")
        candidate = argv[0]
        path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
        if not path or not pathlib.Path(path).is_file() or not os.access(path, os.X_OK):
            raise RuntimeError(f"M4 is not executable: {candidate}")
        gnu_m4_version(str(path))
        return str(path)

    if platform.system() == "Darwin":
        for candidate in (
            "/opt/homebrew/opt/m4/bin/m4",
            "/usr/local/opt/m4/bin/m4",
        ):
            if pathlib.Path(candidate).is_file() and os.access(candidate, os.X_OK):
                add_candidate(candidate)

        brew = shutil.which("brew")
        if brew:
            completed = subprocess.run(
                [brew, "--prefix", "m4"],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                check=False,
            )
            if completed.returncode == 0:
                prefix = completed.stdout.strip()
                candidate = pathlib.Path(prefix) / "bin" / "m4" if prefix else None
                if candidate and candidate.is_file() and os.access(candidate, os.X_OK):
                    add_candidate(str(candidate))

    names = ("gm4", "m4") if platform.system() == "Darwin" else ("m4", "gm4")
    for name in names:
        path = shutil.which(name)
        if path:
            add_candidate(path)

    rejected: list[str] = []
    for path in candidates:
        try:
            gnu_m4_version(path)
        except RuntimeError as exc:
            rejected.append(str(exc))
            continue
        return path

    detail = "; ".join(rejected) if rejected else "no candidates found"
    raise RuntimeError(
        "GNU M4 with --gnu support is required to bootstrap libisofs: " + detail
    )


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


def resolve_autotool(env_name: str, default_name: str) -> str:
    requested = os.environ.get(env_name, "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError(f"{env_name} must name exactly one executable")
        candidate = argv[0]
    else:
        candidate = default_name

    path = (
        candidate
        if pathlib.Path(candidate).is_absolute()
        else shutil.which(candidate)
    )
    if not path or not pathlib.Path(path).is_file() or not os.access(path, os.X_OK):
        raise RuntimeError(f"{env_name or default_name} is not executable: {candidate}")
    return str(path)


def gnu_automake_version(path: str) -> str:
    line = run_text([path, "--version"]).splitlines()[0]
    if "GNU automake" not in line:
        raise RuntimeError(f"not a GNU Automake tool: {path}: {line}")
    version = line.rsplit(" ", 1)[-1]
    if not version_tuple(version):
        raise RuntimeError(f"could not parse GNU Automake version: {path}: {line}")
    return version


def select_automake_pair() -> tuple[str, str, str]:
    if bool(os.environ.get("AUTOMAKE")) != bool(os.environ.get("ACLOCAL")):
        raise RuntimeError("AUTOMAKE and ACLOCAL must be supplied as a pair")

    automake = resolve_autotool("AUTOMAKE", "automake")
    aclocal = resolve_autotool("ACLOCAL", "aclocal")
    automake_version = gnu_automake_version(automake)
    aclocal_version = gnu_automake_version(aclocal)
    if automake_version != aclocal_version:
        raise RuntimeError(
            "AUTOMAKE and ACLOCAL must come from the same GNU Automake "
            f"version: {automake_version} != {aclocal_version}"
        )
    return automake, aclocal, automake_version


def gnu_autoconf_version(path: str) -> str:
    line = run_text([path, "--version"]).splitlines()[0]
    if "GNU Autoconf" not in line:
        raise RuntimeError(f"not GNU Autoconf: {path}: {line}")
    version = line.rsplit(" ", 1)[-1]
    parsed = version_tuple(version)
    if not parsed:
        raise RuntimeError(f"could not parse GNU Autoconf version: {path}: {line}")
    if parsed < (2, 69):
        raise RuntimeError(
            f"GNU Autoconf 2.69 or newer is required by libisofs; found {version}"
        )
    return version


def select_autoconf() -> tuple[str, str]:
    autoconf = resolve_autotool("AUTOCONF", "autoconf")
    return autoconf, gnu_autoconf_version(autoconf)

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


def libisofs_c_policy_flags() -> list[str]:
    return [
        f"-std={LIBISOFS_C_STANDARD}",
        "-Werror=strict-prototypes",
    ]


def libisofs_cpp_policy_flags(host_system: str | None = None) -> list[str]:
    """Return dependency-owned preprocessor inputs, never probe results."""
    system = host_system or platform.system()
    if system == "Darwin":
        return ["-D_DARWIN_C_SOURCE=1"]
    return []


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
#include <sys/stat.h>
#include <time.h>
#include <libisofs.h>
#ifdef __APPLE__
#ifndef __has_feature
#define __has_feature(x) 0
#endif
_Static_assert(sizeof(void *) == 8, "Darwin data pointers must be 64-bit");
_Static_assert(sizeof(size_t) == 8, "Darwin size_t must be 64-bit");
_Static_assert(sizeof(ssize_t) == 8, "Darwin ssize_t must be 64-bit");
_Static_assert(sizeof(off_t) == 8, "Darwin off_t must be 64-bit");
_Static_assert(sizeof(time_t) == 8, "Darwin time_t must be 64-bit");
_Static_assert(sizeof(ino_t) == 8, "Darwin ino_t must be 64-bit");
_Static_assert(sizeof(iso_node_xinfo_func) == sizeof(void *),
               "Darwin function pointer width drifted");
#if defined(__arm64e__) && !__has_feature(ptrauth_calls)
#error arm64e consumer without pointer-authenticated calls
#endif
#endif
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
                *libisofs_c_policy_flags(),
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

def select_macho_lipo() -> str:
    requested = os.environ.get("LIPO", "")
    if requested:
        argv = shlex.split(requested)
        if len(argv) != 1:
            raise RuntimeError("LIPO must name exactly one executable")
        candidate = argv[0]
        path = (
            candidate
            if pathlib.Path(candidate).is_absolute()
            else shutil.which(candidate)
        )
        if not path or not pathlib.Path(path).is_file():
            raise RuntimeError(f"LIPO is not executable: {candidate}")
        return str(path)

    for name in ("llvm-lipo", "lipo"):
        path = shutil.which(name)
        if path:
            return path

    xcrun = shutil.which("xcrun")
    if xcrun:
        path = run_text([xcrun, "--sdk", "macosx", "--find", "lipo"])
        if path:
            return path

    raise RuntimeError("lipo/llvm-lipo is required to verify macOS libisofs ABI")


def macho_archive_architectures(archive: pathlib.Path) -> tuple[str, ...]:
    lipo = select_macho_lipo()
    output = run_text([lipo, "-archs", str(archive)])
    architectures = tuple(output.split())
    if not architectures:
        raise RuntimeError(
            f"lipo returned no architecture for libisofs archive: {archive}"
        )
    return architectures


def verify_macho_archive_architecture(
    archive: pathlib.Path,
    arch: str,
) -> None:
    if platform.system() != "Darwin":
        return
    architectures = macho_archive_architectures(archive)
    if architectures != (arch,):
        found = " ".join(architectures)
        raise RuntimeError(
            f"libisofs archive Mach-O ABI mismatch: expected only {arch}, "
            f"found {found}: {archive}"
        )


def prune_private_install_metadata(prefix: pathlib.Path) -> None:
    for candidate in prefix.glob("**/libisofs.la"):
        if candidate.is_file() or candidate.is_symlink():
            candidate.unlink()


def verify_private_install_surface(prefix: pathlib.Path) -> None:
    archive = find_static_library(prefix)
    if archive is None:
        raise RuntimeError(
            f"libisofs private install lost its static archive: {prefix}"
        )

    header = prefix / "include" / "libisofs" / "libisofs.h"
    if not header.is_file():
        raise RuntimeError(
            f"libisofs private install lost its public header: {header}"
        )

    pc_file = find_pkgconfig_file(prefix)
    if pc_file is None:
        raise RuntimeError(
            f"libisofs private install lost libisofs-1.pc: {prefix}"
        )

    forbidden: list[pathlib.Path] = []
    for pattern in (
        "**/doc/html",
        "**/demo",
        "**/*.dylib",
        "**/*.so",
        "**/libisofs.la",
    ):
        forbidden.extend(prefix.glob(pattern))
    if forbidden:
        rendered = ", ".join(str(path) for path in forbidden)
        raise RuntimeError(
            "libisofs private install unexpectedly contains non-private "
            f"artifacts: {rendered}"
        )

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

    if arch in ("arm64", "arm64e"):
        deployment_version = version_tuple(deployment)
        if not deployment_version or deployment_version[0] < 11:
            raise RuntimeError(
                f"{arch} requires MACOSX_DEPLOYMENT_TARGET >= 11.0, "
                f"not {deployment}"
            )

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


def workspace_marker_text(
    cc: str,
    cc_id: str,
    sdkroot: str,
    arch: str,
    deployment: str,
    config_shell: str,
    libtoolize: str,
    libtoolize_id: str,
    automake: str,
    aclocal: str,
    automake_version: str,
    autoconf: str,
    autoconf_version: str,
    m4: str,
    m4_id: str,
    sed: str,
    cflags: str,
    cppflags: str,
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
        f"AUTOMAKE={automake}\n"
        f"ACLOCAL={aclocal}\n"
        f"AUTOMAKE_VERSION={automake_version}\n"
        f"AUTOCONF={autoconf}\n"
        f"AUTOCONF_VERSION={autoconf_version}\n"
        "ACLOCAL_PATH=ISOLATED\n"
        f"M4={m4}\n"
        f"M4_VERSION={m4_id}\n"
        f"SED={sed}\n"
        f"CFLAGS={cflags}\n"
        f"CPPFLAGS={cppflags}\n"
        f"LDFLAGS={ldflags}\n"
        "CXXFLAGS=UNUSED\n"
        "LINKER_POLICY=COMPILER_DEFAULT\n"
        f"CONFIGURE_ARGS={shlex.join(LIBISOFS_CONFIGURE_ARGS)}\n"
        f"INSTALL_TARGETS={shlex.join(LIBISOFS_INSTALL_TARGETS)}\n"
        "STRICT_PROTOTYPES=1\n"
        "SHARED=0\n"
        "STATIC=1\n"
    )


def marker_text(revision: str, workspace_marker: str) -> str:
    return workspace_marker + f"LIBISOFS_GIT_COMMIT={revision}\n"


def prune_qemu_bootstrap_source(source: pathlib.Path) -> None:
    """Remove maintainer-only material after Autotools generated the build."""
    for relative in QEMU_UNUSED_SOURCE_DIRS:
        shutil.rmtree(source / relative, ignore_errors=True)

    for relative in QEMU_UNUSED_SOURCE_FILES:
        path = source / relative
        try:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
        except FileNotFoundError:
            pass

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
    if version_tuple(installed_version(pc_file)) < LIBISOFS_MIN_VERSION:
        return False
    try:
        verify_private_install_surface(prefix)
    except RuntimeError:
        return False
    return True


def bootstrap(build_root: pathlib.Path, cc: str) -> pathlib.Path:
    revision = ensure_libisofs_source()
    make = select_gnu_make()
    libtoolize = select_gnu_libtool(
        "LIBTOOLIZE", ("glibtoolize", "libtoolize")
    )
    config_shell = select_config_shell()
    sdkroot, arch, deployment = macos_settings()
    cc_id = compiler_version(cc)
    libtoolize_id = run_text([libtoolize, "--version"]).splitlines()[0]
    automake, aclocal, automake_version = select_automake_pair()
    autoconf, autoconf_version = select_autoconf()
    m4 = select_gnu_m4()
    m4_id = gnu_m4_version(m4)
    sed = select_sed()
    incremental = incremental_build_enabled()

    work_dir = build_root / "bootstrap" / "libisofs"
    source_copy = work_dir / "source"
    object_dir = work_dir / "build"
    prefix = build_root / "deps" / "libisofs"

    env = os.environ.copy()
    # Autoconf/Automake must own their portable install/mkdir/symlink
    # variables. A QEMU caller can intentionally select compiler/binutils
    # tools, but must not replace commands generated for this source tree.
    isolate_autotools_utility_env(env)
    isolate_dependency_flag_env(env)

    # LIBTOOL is project-generated. LD is intentionally isolated above too:
    # QEMU may export native ld64.lld, while libisofs Darwin/arm64e configure
    # and link probes must let the selected Clang driver choose its platform
    # linker unless libisofs itself explicitly gains a linker policy.
    env.pop("LIBTOOL", None)
    env["CC"] = cc
    env["LIBTOOLIZE"] = libtoolize
    env["AUTOMAKE"] = automake
    env["ACLOCAL"] = aclocal
    env["AUTOCONF"] = autoconf
    env["ACLOCAL_PATH"] = ""
    autotools_dirs = [
        str(pathlib.Path(automake).parent),
        str(pathlib.Path(autoconf).parent),
    ]
    env["PATH"] = os.pathsep.join(
        list(dict.fromkeys(autotools_dirs)) + [env.get("PATH", "")]
    )
    env["M4"] = m4
    env["SED"] = sed
    env["CONFIG_SHELL"] = config_shell
    env["SHELL"] = config_shell
    compile_flags = ["-O3", *libisofs_c_policy_flags()]
    cpp_flags = libisofs_cpp_policy_flags()
    dependency_link_flags: list[str] = []
    zlib_prefix_value = os.environ.get("WHP_ZLIB_PREFIX", "").strip()
    if zlib_prefix_value:
        zlib_prefix = pathlib.Path(zlib_prefix_value).expanduser().resolve()
        zlib_include = zlib_prefix / "include"
        zlib_lib = zlib_prefix / "lib"
        if not (zlib_include / "zlib.h").is_file():
            raise RuntimeError(
                f"WHP_ZLIB_PREFIX has no zlib.h: {zlib_prefix}"
            )
        if not (zlib_lib / "libz.a").is_file():
            raise RuntimeError(
                f"WHP_ZLIB_PREFIX has no static libz.a: {zlib_prefix}"
            )
        cpp_flags.append(f"-I{zlib_include}")
        dependency_link_flags.append(f"-L{zlib_lib}")
    if sdkroot:
        compile_flags += [
            "-arch", arch,
            "-isysroot", sdkroot,
            f"-mmacosx-version-min={deployment}",
        ]
        env["SDKROOT"] = sdkroot
        env["MACOSX_DEPLOYMENT_TARGET"] = deployment

    # CFLAGS carries the Darwin ABI triplet through compile and the
    # compiler-driver link commands. LDFLAGS stays empty so those flags are
    # not duplicated and QEMU-specific linker policy cannot leak in.
    env["CFLAGS"] = " ".join(compile_flags)
    env["CPPFLAGS"] = " ".join(cpp_flags)
    env["LDFLAGS"] = " ".join(dependency_link_flags)

    workspace_marker = workspace_marker_text(
        cc,
        cc_id,
        sdkroot,
        arch,
        deployment,
        config_shell,
        libtoolize,
        libtoolize_id,
        automake,
        aclocal,
        automake_version,
        autoconf,
        autoconf_version,
        m4,
        m4_id,
        sed,
        env["CFLAGS"],
        env["CPPFLAGS"],
        env["LDFLAGS"],
    )
    marker = marker_text(revision, workspace_marker)
    if incremental and cache_valid(prefix, marker):
        archive = find_static_library(prefix)
        if archive is None:
            raise RuntimeError(
                f"cached libisofs prefix lost its static archive: {prefix}"
            )
        verify_macho_archive_architecture(archive, arch)
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
    prune_qemu_bootstrap_source(source_copy)

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
        [make, "-j", str(max(1, int(os.environ.get("JOBS", os.cpu_count() or 1))))],
        cwd=object_dir,
        env=env,
    )
    run_logged([make, *LIBISOFS_INSTALL_TARGETS], cwd=object_dir, env=env)

    prune_private_install_metadata(prefix)
    verify_private_install_surface(prefix)
    archive = find_static_library(prefix)
    assert archive is not None
    verify_macho_archive_architecture(archive, arch)

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
    isolate_dependency_flag_env(probe_env)
    pc_dir = str(pc_file.parent)
    # Validate exactly the private install. An inherited pkg-config sysroot or
    # search path could otherwise make the smoke test pass against another
    # libisofs or dependency set.
    probe_env["PKG_CONFIG_PATH"] = pc_dir
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
        link_flags=dependency_link_flags,
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
