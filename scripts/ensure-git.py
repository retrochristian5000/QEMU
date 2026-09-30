#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP Git fork without hiding Git's bootstrap cycle."""

from __future__ import annotations

import argparse
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
import tempfile
from typing import List

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/git")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SHA1_REL = pathlib.Path("sha1collisiondetection")
GIT_ADAPTER = ROOT / "git.sh"
GIT_BOOTSTRAP_SCHEMA = "1"


def run_text(command: List[str], *, cwd=None, env=None) -> str:
    completed = subprocess.run(
        command, cwd=cwd, env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(
            f"command failed: {shlex.join(command)}"
            + (f": {detail}" if detail else "")
        )
    return completed.stdout.strip()


def run_logged(command: List[str], *, cwd=None, env=None) -> None:
    completed = subprocess.run(
        command, cwd=cwd, env=env,
        stdout=sys.stderr, stderr=sys.stderr, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit status {completed.returncode}: "
            + shlex.join(command)
        )


def executable(value: str) -> str | None:
    if not value:
        return None
    path = value if pathlib.Path(value).is_absolute() else shutil.which(value)
    if path and pathlib.Path(path).is_file() and os.access(path, os.X_OK):
        return os.path.abspath(path)
    return None


def explicit_tool(name: str) -> str | None:
    value = os.environ.get(name, "")
    if not value:
        return None
    argv = shlex.split(value)
    if len(argv) != 1:
        raise RuntimeError(f"{name} must name exactly one executable")
    path = executable(argv[0])
    if not path:
        raise RuntimeError(f"{name} is not executable: {argv[0]}")
    return path


def seed_git() -> str:
    if not GIT_ADAPTER.is_file() or not os.access(GIT_ADAPTER, os.X_OK):
        raise RuntimeError(f"QEMU Git seed adapter is unavailable: {GIT_ADAPTER}")
    completed = subprocess.run(
        [str(GIT_ADAPTER), "--print-seed"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, env=os.environ.copy(),
    )
    path = completed.stdout.strip()
    if completed.returncode != 0 or not path:
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU git.sh could not resolve the Git bootstrap seed"
            + (f": {detail}" if detail else "")
        )
    return path


def select_gnu_make() -> str:
    requested = explicit_tool("MAKE_CMD") or explicit_tool("MAKE")
    candidates = [requested] if requested else [
        p for p in (executable("gmake"), executable("make")) if p
    ]
    for path in candidates:
        output = subprocess.run(
            [path, "--version"], text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
        )
        if output.returncode == 0 and "GNU Make" in output.stdout:
            return path
    raise RuntimeError("GNU Make is required to bootstrap the WHP Git fork")


def select_cc() -> str:
    requested = explicit_tool("CC_FOR_BUILD")
    if requested:
        return requested

    adapter = ROOT / "cc.sh"
    if adapter.is_file() and os.access(adapter, os.X_OK):
        completed = subprocess.run(
            [str(adapter), "--print-cc"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        candidate = completed.stdout.strip()
        if completed.returncode == 0 and candidate:
            return candidate
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU cc.sh could not resolve the Git bootstrap compiler"
            + (f": {detail}" if detail else "")
        )

    raise RuntimeError("a native build C compiler is required to bootstrap Git")


def gitlink(seed: str, repo: pathlib.Path, relpath: pathlib.Path) -> str:
    line = run_text([seed, "-C", str(repo), "ls-tree", "HEAD", "--", str(relpath)])
    fields = line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(f"Git gitlink is not registered: {repo}:{relpath}")
    return fields[2]


def ensure_source(seed: str) -> tuple[str, str]:
    revision = gitlink(seed, ROOT, SUBMODULE_REL)
    current = ""
    if (SUBMODULE_DIR / ".git").exists():
        current = run_text([seed, "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
    if current != revision:
        run_logged([
            seed, "-C", str(ROOT), "submodule", "update", "--init",
            "--depth", "1", "--", str(SUBMODULE_REL),
        ])
        current = run_text([seed, "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
    if current != revision:
        raise RuntimeError(
            f"Git submodule revision mismatch: {current} != {revision}"
        )

    sha1_revision = gitlink(seed, SUBMODULE_DIR, SHA1_REL)
    run_logged([
        seed, "-C", str(SUBMODULE_DIR), "submodule", "sync", "--", str(SHA1_REL),
    ])
    run_logged([
        seed, "-C", str(SUBMODULE_DIR), "submodule", "update", "--init",
        "--depth", "1", "--", str(SHA1_REL),
    ])
    sha1_dir = SUBMODULE_DIR / SHA1_REL
    sha1_current = run_text([seed, "-C", str(sha1_dir), "rev-parse", "HEAD"])
    if sha1_current != sha1_revision:
        raise RuntimeError(
            "Git SHA-1 collision submodule revision mismatch: "
            f"{sha1_current} != {sha1_revision}"
        )
    return revision, sha1_revision


def archive(seed: str, repo: pathlib.Path, revision: str, destination: pathlib.Path) -> None:
    completed = subprocess.run(
        [seed, "-C", str(repo), "archive", "--format=tar", revision],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(
            f"could not archive {repo} at {revision}"
            + (f": {detail}" if detail else "")
        )
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as tf:
        tf.extractall(destination)


def source_version() -> str:
    text = (SUBMODULE_DIR / "GIT-VERSION-GEN").read_text(
        encoding="utf-8", errors="replace"
    )
    match = re.search(r"(?m)^DEF_VER=(v[^\s]+)$", text)
    return match.group(1) if match else "v0.0.GIT"


def copy_source(seed, revision, sha1_revision, destination) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    archive(seed, SUBMODULE_DIR, revision, destination)
    archive(
        seed, SUBMODULE_DIR / SHA1_REL, sha1_revision,
        destination / SHA1_REL,
    )
    (destination / "version").write_text(source_version() + "\n", encoding="utf-8")


def curl_prefix() -> str:
    explicit = os.environ.get("WHP_GIT_CURLDIR", "")
    if explicit:
        path = pathlib.Path(explicit).expanduser().resolve()
        if not (path / "include" / "curl").is_dir():
            raise RuntimeError(f"WHP_GIT_CURLDIR lacks curl headers: {path}")
        return str(path)
    curl_config = shutil.which("curl-config")
    if not curl_config:
        return ""
    try:
        prefix = run_text([curl_config, "--prefix"])
    except RuntimeError:
        return ""
    path = pathlib.Path(prefix)
    if (path / "include" / "curl").is_dir():
        return str(path)
    return ""


def iconv_prefix() -> str:
    if platform.system() != "Darwin":
        return ""

    explicit = os.environ.get("WHP_GIT_ICONVDIR", "")
    candidates = []
    if explicit:
        candidates.append(pathlib.Path(explicit).expanduser().resolve())
    candidates.extend((
        pathlib.Path("/opt/homebrew/opt/libiconv"),
        pathlib.Path("/usr/local/opt/libiconv"),
    ))
    for path in candidates:
        if (path / "include" / "iconv.h").is_file():
            return str(path)

    release = platform.release().split(".", 1)[0]
    try:
        darwin_major = int(release)
    except ValueError:
        darwin_major = 0
    if darwin_major >= 24:
        raise RuntimeError(
            "Git PRECOMPOSE_UNICODE requires usable iconv on Darwin 24+; "
            "install Homebrew libiconv or set WHP_GIT_ICONVDIR"
        )
    return ""


def git_usable(path: pathlib.Path) -> bool:
    if not path.is_file() or not os.access(path, os.X_OK):
        return False
    completed = subprocess.run(
        [str(path), "--version"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    return completed.returncode == 0 and completed.stdout.startswith("git version ")


def has_https_transport(git_path: pathlib.Path) -> bool:
    if not git_usable(git_path):
        return False
    completed = subprocess.run(
        [str(git_path), "--exec-path"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    if completed.returncode != 0:
        return False
    return (pathlib.Path(completed.stdout.strip()) / "git-remote-https").exists()


def smoke_local(git_path: pathlib.Path) -> bool:
    with tempfile.TemporaryDirectory(prefix="whp-git-smoke-") as td:
        repo = pathlib.Path(td)
        commands = (
            [str(git_path), "init", "-q", str(repo)],
            [str(git_path), "-C", str(repo), "config", "user.name", "WHP Git"],
            [str(git_path), "-C", str(repo), "config", "user.email", "whp@example.invalid"],
        )
        for command in commands:
            if subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                return False
        (repo / "probe").write_text("git bootstrap probe\n", encoding="utf-8")
        for command in (
            [str(git_path), "-C", str(repo), "add", "probe"],
            [str(git_path), "-C", str(repo), "commit", "-q", "-m", "probe"],
            [str(git_path), "-C", str(repo), "rev-parse", "--verify", "HEAD"],
        ):
            if subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode:
                return False
    return True


def marker_text(revision, sha1_revision, seed, cc, make, profile, curl_dir, iconv_dir) -> str:
    return (
        f"GIT_BOOTSTRAP_SCHEMA={GIT_BOOTSTRAP_SCHEMA}\n"
        f"GIT_GIT_COMMIT={revision}\n"
        f"SHA1COLLISION_GIT_COMMIT={sha1_revision}\n"
        f"SEED_GIT={seed}: {run_text([seed, '--version']).splitlines()[0]}\n"
        f"CC={cc}: {run_text([cc, '--version']).splitlines()[0]}\n"
        f"MAKE={make}: {run_text([make, '--version']).splitlines()[0]}\n"
        f"PROFILE={profile}\n"
        f"CURLDIR={curl_dir}\n"
        f"ICONVDIR={iconv_dir}\n"
    )


def build_profile(seed, revision, sha1_revision, cc, make, build_root, profile, curl_dir, iconv_dir):
    prefix = build_root / "deps" / "git"
    work = build_root / "bootstrap" / "git"
    source = work / "source"
    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(seed, revision, sha1_revision, source)

    env = os.environ.copy()
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT",
        "CFLAGS", "CPPFLAGS", "LDFLAGS",
        "AR", "AS", "LD", "NM", "RANLIB", "STRIP",
        "GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE",
    ):
        env.pop(key, None)
    env["CC"] = cc
    env["GIT_BUILT_FROM_COMMIT"] = revision

    variables = [
        f"prefix={prefix}", f"CC={cc}",
        "NO_GETTEXT=YesPlease", "NO_PERL=YesPlease", "NO_PYTHON=YesPlease",
        "NO_TCLTK=YesPlease", "NO_GITWEB=YesPlease", "NO_EXPAT=YesPlease",
        "NO_OPENSSL=YesPlease",
        "NO_INSTALL_HARDLINKS=YesPlease", "DC_SHA1_SUBMODULE=YesPlease",
    ]
    if profile == "core":
        variables.append("NO_CURL=YesPlease")
    elif curl_dir:
        variables.append(f"CURLDIR={curl_dir}")

    if iconv_dir:
        variables.extend((
            "USE_HOMEBREW_LIBICONV=YesPlease",
            f"ICONVDIR={iconv_dir}",
        ))

    print(
        f"WHP Git bootstrap: {revision} -> {prefix} "
        f"(profile {profile}, seed {seed})",
        file=sys.stderr,
    )
    run_logged(
        [make, "-C", str(source), "-j", str(max(1, os.cpu_count() or 1)), *variables],
        env=env,
    )
    run_logged([make, "-C", str(source), "install", *variables], env=env)

    git_path = prefix / "bin" / "git"
    if not git_usable(git_path) or not smoke_local(git_path):
        raise RuntimeError(f"bootstrapped Git failed local checks: {git_path}")
    return prefix


def bootstrap(build_root: pathlib.Path, mode: str) -> pathlib.Path:
    seed = seed_git()
    revision, sha1_revision = ensure_source(seed)
    cc = select_cc()
    make = select_gnu_make()
    curl_dir = curl_prefix()
    iconv_dir = iconv_prefix()
    prefix = build_root / "deps" / "git"
    marker_path = prefix / ".whp-git-bootstrap"
    git_path = prefix / "bin" / "git"

    profiles = ["full"] if mode == "force" else ["full", "core"]
    if mode == "core":
        profiles = ["core"]

    for profile in profiles:
        marker = marker_text(
            revision, sha1_revision, seed, cc, make, profile,
            curl_dir if profile == "full" else "",
            iconv_dir,
        )
        if (
            marker_path.is_file()
            and marker_path.read_text(encoding="utf-8", errors="replace") == marker
            and git_usable(git_path)
            and smoke_local(git_path)
            and (profile != "full" or has_https_transport(git_path))
        ):
            return prefix

        try:
            built = build_profile(
                seed, revision, sha1_revision, cc, make, build_root,
                profile, curl_dir if profile == "full" else "", iconv_dir,
            )
        except RuntimeError:
            if mode == "force" or profile == profiles[-1]:
                raise
            print(
                "WHP Git full profile unavailable; retrying local profile",
                file=sys.stderr,
            )
            continue

        git_path = built / "bin" / "git"
        if profile == "full" and not has_https_transport(git_path):
            if mode == "force":
                raise RuntimeError("forced WHP Git build lacks git-remote-https")
            continue

        marker_path = built / ".whp-git-bootstrap"
        marker_path.write_text(marker, encoding="utf-8")
        return built

    raise RuntimeError("no WHP Git bootstrap profile succeeded")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", choices=("auto", "force", "core"), default="auto")
    args = parser.parse_args(argv)
    if platform.system() == "Windows":
        print("error: WHP Git bootstrap currently requires a POSIX host", file=sys.stderr)
        return 1
    try:
        prefix = bootstrap(
            pathlib.Path(args.build_dir).expanduser().resolve(), args.mode
        )
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP Git bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
