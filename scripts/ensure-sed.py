#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP GNU sed as a deterministic host-side build tool.

GNU sed's own Git bootstrap uses sed, so this is intentionally a two-stage
bootstrap: a host sed is the seed only while the pinned GNU sed is generated
and built.  The caller then publishes the validated GNU sed through SED/PATH.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import platform
import re
import shlex
import shutil
import subprocess
import sys
import tarfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/sed")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
NESTED_REL = pathlib.Path("gnulib")
SED_ADAPTER = ROOT / "sed.sh"
SED_BOOTSTRAP_SCHEMA = "3"


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


def explicit_executable(env_name: str) -> str | None:
    requested = os.environ.get(env_name, "")
    if not requested:
        return None
    argv = shlex.split(requested)
    if len(argv) != 1:
        raise RuntimeError(f"{env_name} must name exactly one executable")
    path = executable(argv[0])
    if not path:
        raise RuntimeError(f"{env_name} is not executable: {argv[0]}")
    return path


def semantic_sed_usable(path: str) -> bool:
    probes = (
        ("alpha\n", ["-n", "s/^alpha$/beta/p"], "beta\n"),
        ("A B/C\n", ["s,[^A-Za-z0-9_.-],-,g"], "A-B-C\n"),
        ("AR=/tmp/llvm-ar|LLVM\n", ["-n", r"s#^AR=\([^|]*\)|.*$#\1#p"], "/tmp/llvm-ar\n"),
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


def gnu_sed_usable(path: str) -> bool:
    if not semantic_sed_usable(path):
        return False
    completed = subprocess.run(
        [path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return completed.returncode == 0 and "GNU sed" in completed.stdout


def seed_sed() -> str:
    if not SED_ADAPTER.is_file() or not os.access(SED_ADAPTER, os.X_OK):
        raise RuntimeError(f"QEMU sed seed adapter is unavailable: {SED_ADAPTER}")

    completed = subprocess.run(
        [str(SED_ADAPTER), "--print-seed"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
        env=os.environ.copy(),
    )
    seed = completed.stdout.strip()
    if completed.returncode != 0 or not seed:
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU sed.sh could not resolve the GNU sed bootstrap seed"
            + (f": {detail}" if detail else "")
        )
    if not semantic_sed_usable(seed):
        raise RuntimeError(f"resolved seed sed failed semantic probes: {seed}")
    return seed


def command_path(
    name: str,
    env_name: str | None = None,
    aliases: tuple[str, ...] = (),
) -> str:
    requested = explicit_executable(env_name) if env_name else None
    if requested:
        return requested
    for candidate in (name, *aliases):
        path = executable(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap GNU sed")


def select_gnu_make() -> str:
    requested = explicit_executable("MAKE_CMD") or explicit_executable("MAKE")
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
    raise RuntimeError("GNU Make is required to bootstrap GNU sed")


def select_cc() -> str:
    requested = explicit_executable("CC")
    if requested:
        return requested
    if platform.system() == "Darwin" and shutil.which("xcrun"):
        return run_text(["xcrun", "--sdk", "macosx", "--find", "clang"])
    for name in ("cc", "clang", "gcc"):
        path = executable(name)
        if path:
            return path
    raise RuntimeError("a host C compiler is required to bootstrap GNU sed")


def compiler_version(cc: str) -> str:
    return run_text([cc, "--version"]).splitlines()[0]


def seed_identity(path: str) -> str:
    completed = subprocess.run(
        [path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    first = completed.stdout.splitlines()[0] if completed.stdout else "<no version>"
    return f"{path}: {first}"


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def gitlink_revision(repo: pathlib.Path, relpath: pathlib.Path) -> str:
    line = run_text(["git", "-C", str(repo), "ls-tree", "HEAD", "--", str(relpath)])
    fields = line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(f"gitlink is not registered in {repo}: {relpath}")
    return fields[2]


def archive_source_signature() -> tuple[str, str]:
    required = (
        SUBMODULE_DIR / "bootstrap",
        SUBMODULE_DIR / "bootstrap.conf",
        SUBMODULE_DIR / "configure.ac",
        SUBMODULE_DIR / "Makefile.am",
    )
    for path in required:
        if not path.is_file():
            raise RuntimeError(
                f"bundled GNU sed source is unavailable: {SUBMODULE_DIR}"
            )
    nested = SUBMODULE_DIR / NESTED_REL
    if not (nested / "gnulib-tool").is_file():
        raise RuntimeError(
            f"bundled GNU sed gnulib source is unavailable: {nested}"
        )

    digest = hashlib.sha256()
    for path in required:
        digest.update(path.read_bytes())
        digest.update(b"\0")
    digest.update((nested / "gnulib-tool").read_bytes())
    return f"archive-{digest.hexdigest()}", "archive-nested"


def ensure_source() -> tuple[str, str]:
    if not git_checkout_available():
        return archive_source_signature()

    revision = gitlink_revision(ROOT, SUBMODULE_REL)
    current = ""
    if (SUBMODULE_DIR / ".git").exists():
        try:
            current = run_text(["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
        except RuntimeError:
            current = ""
    if current != revision:
        run_logged([
            "git", "-C", str(ROOT), "submodule", "update", "--init",
            "--depth", "1", str(SUBMODULE_REL),
        ])
        current = run_text(["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
    if current != revision:
        raise RuntimeError(
            f"GNU sed submodule revision mismatch: {current} != {revision}"
        )

    nested_revision = gitlink_revision(SUBMODULE_DIR, NESTED_REL)
    run_logged([
        "git", "-C", str(SUBMODULE_DIR), "submodule", "sync", "--",
        str(NESTED_REL),
    ])
    run_logged([
        "git", "-C", str(SUBMODULE_DIR), "submodule", "update", "--init",
        "--depth", "1", "--", str(NESTED_REL),
    ])
    nested_dir = SUBMODULE_DIR / NESTED_REL
    nested_current = run_text(["git", "-C", str(nested_dir), "rev-parse", "HEAD"])
    if nested_current != nested_revision:
        raise RuntimeError(
            "GNU sed gnulib revision mismatch: "
            f"{nested_current} != {nested_revision}"
        )

    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        raise RuntimeError(
            "GNU sed submodule has tracked changes; commit them in the sed fork "
            "and update the QEMU gitlink"
        )
    return revision, nested_revision


def extract_git_archive(
    repo: pathlib.Path, revision: str, destination: pathlib.Path
) -> None:
    completed = subprocess.run(
        ["git", "-C", str(repo), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"could not archive {repo} at {revision}"
            + (f": {detail}" if detail else "")
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
        archive.extractall(destination)


def latest_release_version() -> str:
    """Return the newest numbered release documented in sed's NEWS file."""
    news = (SUBMODULE_DIR / "NEWS").read_text(
        encoding="utf-8", errors="replace"
    )
    match = re.search(
        r"(?m)^\\* Noteworthy changes in release "
        r"([0-9]+(?:\\.[0-9]+)+) \\(",
        news,
    )
    return match.group(1) if match else "0"


def fallback_staged_version(revision: str) -> str:
    """Return a truthful deterministic version when Git history is incomplete."""
    base = latest_release_version()
    if revision.startswith("archive-"):
        identity = revision.removeprefix("archive-")[:12]
        kind = "archive"
    else:
        identity = revision[:12]
        kind = "git"
    identity = re.sub(r"[^0-9A-Za-z]+", "", identity) or "unknown"
    return f"{base}.{kind}-{identity}"


def live_checkout_version(revision: str) -> str:
    """Use gnulib's version generator from the live sed checkout.

    GNU sed does not track build-aux/git-version-gen directly. bootstrap.conf
    imports it from the pinned gnulib submodule before Autoconf evaluates
    configure.ac. QEMU needs a version earlier because it converts the live
    checkout into an isolated git-archive tree, so use that exact gnulib
    helper against the live checkout and persist its answer as
    .tarball-version in the staged tree.
    """
    version_helper = (
        SUBMODULE_DIR / NESTED_REL / "build-aux" / "git-version-gen"
    )
    if not version_helper.is_file():
        raise RuntimeError(
            "pinned gnulib lacks build-aux/git-version-gen: "
            f"{version_helper}"
        )

    version = run_text(
        [
            "/bin/sh",
            str(version_helper),
            str(SUBMODULE_DIR / ".tarball-version"),
        ],
        cwd=SUBMODULE_DIR,
    ).strip()

    # A shallow submodule may not carry a reachable release tag, in which
    # case upstream git-version-gen correctly reports UNKNOWN. Do not fetch
    # extra history behind the user's back just to name a build; the exact
    # QEMU gitlink is already authoritative, so preserve the newest documented
    # sed release plus the pinned commit identity instead.
    if not version or version == "UNKNOWN":
        version = fallback_staged_version(revision)
    return version


def copy_source(
    revision: str, nested_revision: str, destination: pathlib.Path
) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    if git_checkout_available() and (SUBMODULE_DIR / ".git").exists():
        version = live_checkout_version(revision)
        extract_git_archive(SUBMODULE_DIR, revision, destination)
        extract_git_archive(
            SUBMODULE_DIR / NESTED_REL,
            nested_revision,
            destination / NESTED_REL,
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
    tarball_version = destination / ".tarball-version"
    if not tarball_version.is_file():
        tarball_version.write_text(
            fallback_staged_version(revision) + "\n",
            encoding="utf-8",
        )


def macos_environment(env: dict[str, str]) -> tuple[str, str, str]:
    if platform.system() != "Darwin":
        return "", "", ""

    arch = os.environ.get("WHP_MACOS_ARCH", "auto")
    if arch == "auto":
        return "", "", ""
    if arch not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(f"unsupported WHP_MACOS_ARCH for GNU sed: {arch}")
    if not shutil.which("xcrun"):
        raise RuntimeError("xcrun is required for an explicit macOS sed ABI")

    sdkroot = os.environ.get("SDKROOT") or run_text(
        ["xcrun", "--sdk", "macosx", "--show-sdk-path"]
    )
    deployment = os.environ.get("MACOSX_DEPLOYMENT_TARGET", "")
    if not deployment:
        version = platform.mac_ver()[0]
        parts = version.split(".")
        deployment = ".".join(parts[:2]) if version else "11.0"

    flags = shlex.join([
        "-arch", arch,
        "-isysroot", sdkroot,
        f"-mmacosx-version-min={deployment}",
    ])
    env["CFLAGS"] = flags
    env["LDFLAGS"] = flags
    env["SDKROOT"] = sdkroot
    env["MACOSX_DEPLOYMENT_TARGET"] = deployment
    return sdkroot, arch, deployment


def marker_text(
    revision: str,
    nested_revision: str,
    cc: str,
    seed: str,
    sdkroot: str,
    arch: str,
    deployment: str,
) -> str:
    return (
        f"SED_BOOTSTRAP_SCHEMA={SED_BOOTSTRAP_SCHEMA}\n"
        f"SED_GIT_COMMIT={revision}\n"
        f"GNULIB_GIT_COMMIT={nested_revision}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"CC={cc}\n"
        f"CC_VERSION={compiler_version(cc)}\n"
        f"SEED_SED={seed_identity(seed)}\n"
        f"SDKROOT={sdkroot}\n"
        f"WHP_MACOS_ARCH={arch}\n"
        f"MACOSX_DEPLOYMENT_TARGET={deployment}\n"
    )


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision, nested_revision = ensure_source()
    seed = seed_sed()
    cc = select_cc()
    make = select_gnu_make()

    prefix = build_root / "deps" / "sed"
    work = build_root / "bootstrap" / "sed"
    source = work / "source"
    objects = work / "build"
    sed_path = prefix / "bin" / "sed"
    marker_path = prefix / ".whp-sed-bootstrap"

    env = os.environ.copy()
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT",
        "CFLAGS", "CPPFLAGS", "LDFLAGS",
        "AR", "AS", "LD", "NM", "RANLIB", "STRIP",
    ):
        env.pop(key, None)
    env["CC"] = cc
    env["WHP_SED_SEED"] = seed
    env["SED"] = str(SED_ADAPTER)
    sdkroot, arch, deployment = macos_environment(env)

    marker = marker_text(
        revision, nested_revision, cc, seed, sdkroot, arch, deployment
    )
    if (
        marker_path.is_file()
        and marker_path.read_text(encoding="utf-8", errors="replace") == marker
        and gnu_sed_usable(str(sed_path))
    ):
        return sed_path

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, nested_revision, source)
    objects.mkdir(parents=True, exist_ok=True)

    # Bootstrap scripts invoke literal 'sed'. Put only the QEMU seed adapter
    # at the front of PATH; it delegates to WHP_SED_SEED. This avoids exposing
    # the seed sed's whole system directory, where host Automake or other tools
    # could otherwise shadow managed WHP dependencies.
    seed_bin = work / "seed-bin"
    seed_bin.mkdir(parents=True, exist_ok=True)
    seed_link = seed_bin / "sed"
    try:
        seed_link.symlink_to(SED_ADAPTER)
    except OSError:
        shutil.copy2(SED_ADAPTER, seed_link)
        seed_link.chmod(seed_link.stat().st_mode | 0o111)
    env["PATH"] = str(seed_bin) + os.pathsep + env.get("PATH", "")

    config_shell = executable(os.environ.get("CONFIG_SHELL", "")) or "/bin/sh"
    print(
        f"WHP GNU sed bootstrap: {revision} -> {prefix} "
        f"(seed {seed})",
        file=sys.stderr,
    )
    run_logged(
        [
            config_shell,
            str(source / "bootstrap"),
            "--skip-po",
            "--no-git",
            "--copy",
            f"--gnulib-srcdir={source / NESTED_REL}",
        ],
        cwd=source,
        env=env,
    )

    configure = source / "configure"
    if not configure.is_file():
        raise RuntimeError("GNU sed bootstrap did not generate configure")

    run_logged(
        [
            config_shell,
            str(configure),
            f"--prefix={prefix}",
            "--disable-gcc-warnings",
            "--disable-nls",
        ],
        cwd=objects,
        env=env,
    )
    run_logged(
        [make, "-j", str(max(1, os.cpu_count() or 1))],
        cwd=objects,
        env=env,
    )
    run_logged([make, "install"], cwd=objects, env=env)

    if not gnu_sed_usable(str(sed_path)):
        raise RuntimeError(
            f"bootstrapped GNU sed failed semantic/version checks: {sed_path}"
        )
    marker_path.write_text(marker, encoding="utf-8")
    return sed_path


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args(argv)
    try:
        path = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP GNU sed bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
