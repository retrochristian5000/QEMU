#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP GNU Make as a managed host tool."""

from __future__ import annotations

import argparse
import hashlib
import io
import os
import pathlib
import shlex
import shutil
import subprocess
import sys
import tarfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/make")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SED_ADAPTER = ROOT / "sed.sh"

MAKE_BOOTSTRAP_SCHEMA = "1"
GNULIB_COMMIT = "b22f5a3037712a3c957a03071ce0b219cef4d65b"
GNULIB_URL = "https://github.com/coreutils/gnulib.git"


def run_text(command, *, cwd=None, env=None):
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


def run_logged(command, *, cwd=None, env=None):
    completed = subprocess.run(
        command, cwd=cwd, env=env,
        stdout=sys.stderr, stderr=sys.stderr, check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with exit status {completed.returncode}: "
            + shlex.join(command)
        )


def executable(candidate):
    if not candidate:
        return None
    path = candidate if pathlib.Path(candidate).is_absolute() else shutil.which(candidate)
    if path and pathlib.Path(path).is_file() and os.access(path, os.X_OK):
        return os.path.abspath(path)
    return None


def explicit_tool(env_name):
    value = os.environ.get(env_name, "")
    if not value:
        return None
    argv = shlex.split(value)
    if len(argv) != 1:
        raise RuntimeError(f"{env_name} must name exactly one executable")
    path = executable(argv[0])
    if not path:
        raise RuntimeError(f"{env_name} is not executable: {argv[0]}")
    return path


def tool(name, env_name=None, aliases=()):
    requested = explicit_tool(env_name) if env_name else None
    if requested:
        return requested
    for candidate in (name, *aliases):
        path = executable(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap GNU Make")


def first_line(command):
    output = run_text(command)
    return output.splitlines()[0] if output else ""


def gnu_make_usable(path):
    candidate = pathlib.Path(path)
    if not candidate.is_file() or not os.access(candidate, os.X_OK):
        return False
    completed = subprocess.run(
        [str(candidate), "--version"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    return completed.returncode == 0 and completed.stdout.startswith("GNU Make ")


def select_seed_make():
    requested = explicit_tool("WHP_MAKE_SEED") or explicit_tool("MAKE_CMD") or explicit_tool("MAKE")
    candidates = [requested] if requested else [
        path for path in (executable("gmake"), executable("make")) if path
    ]
    for path in candidates:
        if gnu_make_usable(path):
            return path
    raise RuntimeError("a seed GNU Make is required before the managed GNU Make stage")


def select_automake_pair():
    automake = explicit_tool("AUTOMAKE") or executable("automake")
    aclocal = explicit_tool("ACLOCAL") or executable("aclocal")
    if not automake or not aclocal:
        raise RuntimeError("Automake/aclocal are required to bootstrap GNU Make")
    for path in (automake, aclocal):
        if "GNU automake" not in run_text([path, "--version"]):
            raise RuntimeError(f"not a usable GNU Automake tool: {path}")
    return automake, aclocal


def select_autoconf_suite():
    autoconf = explicit_tool("AUTOCONF") or executable("autoconf")
    autom4te = explicit_tool("AUTOM4TE") or executable("autom4te")
    autoreconf = explicit_tool("AUTORECONF") or executable("autoreconf")
    if not autoconf or not autom4te or not autoreconf:
        raise RuntimeError("Autoconf/autom4te/autoreconf are required to bootstrap GNU Make")
    for path in (autoconf, autom4te, autoreconf):
        if "GNU Autoconf" not in run_text([path, "--version"]):
            raise RuntimeError(f"not a usable GNU Autoconf tool: {path}")
    return autoconf, autom4te, autoreconf


def select_seed_sed():
    requested = explicit_tool("WHP_SED_SEED") or explicit_tool("SED")
    if requested:
        return requested
    completed = subprocess.run(
        [str(SED_ADAPTER), "--print-seed"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    seed = completed.stdout.strip()
    if completed.returncode != 0 or not seed:
        raise RuntimeError("QEMU sed.sh could not resolve the GNU Make bootstrap seed")
    return seed


def select_cc():
    requested = explicit_tool("CC_FOR_BUILD")
    if requested:
        return requested
    completed = subprocess.run(
        [str(ROOT / "cc.sh"), "--print-cc"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    cc = completed.stdout.strip()
    if completed.returncode == 0 and cc:
        return cc
    raise RuntimeError("a native C compiler is required to bootstrap GNU Make")


def git_checkout_available():
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def gitlink_revision():
    fields = run_text([
        "git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL)
    ]).split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError("GNU Make gitlink is not registered in QEMU")
    return fields[2]


def archive_source_signature():
    required = (
        "bootstrap", "bootstrap.conf", "configure.ac", "Makefile.am",
        "build.sh", "build.cfg.in",
    )
    digest = hashlib.sha256()
    for name in required:
        path = SUBMODULE_DIR / name
        if not path.is_file():
            raise RuntimeError(f"bundled GNU Make source is unavailable: {path}")
        digest.update(name.encode())
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "archive-" + digest.hexdigest()


def ensure_source():
    if not git_checkout_available():
        return archive_source_signature()
    revision = gitlink_revision()
    current = ""
    if (SUBMODULE_DIR / ".git").exists():
        try:
            current = run_text(["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
        except RuntimeError:
            pass
    if current != revision:
        run_logged([
            "git", "-C", str(ROOT), "submodule", "update", "--init",
            "--depth", "1", str(SUBMODULE_REL),
        ])
        current = run_text(["git", "-C", str(SUBMODULE_DIR), "rev-parse", "HEAD"])
    if current != revision:
        raise RuntimeError(f"GNU Make submodule revision mismatch: {current} != {revision}")
    dirty = run_text([
        "git", "-C", str(SUBMODULE_DIR), "status", "--porcelain",
        "--untracked-files=no",
    ])
    if dirty:
        raise RuntimeError("GNU Make submodule has tracked changes")
    return revision


def copy_source(revision, destination):
    shutil.rmtree(destination, ignore_errors=True)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if git_checkout_available() and (SUBMODULE_DIR / ".git").exists():
        completed = subprocess.run(
            ["git", "-C", str(SUBMODULE_DIR), "archive", "--format=tar", revision],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        )
        if completed.returncode != 0:
            raise RuntimeError("could not archive pinned GNU Make source")
        destination.mkdir(parents=True, exist_ok=True)
        with tarfile.open(fileobj=io.BytesIO(completed.stdout), mode="r:") as archive:
            archive.extractall(destination)
    else:
        shutil.copytree(SUBMODULE_DIR, destination, ignore=shutil.ignore_patterns(".git"))


def pin_gnulib(source):
    path = source / "bootstrap.conf"
    text = path.read_text(encoding="utf-8")
    old = "GNULIB_REVISION=stable-202507"
    if text.count(old) != 1:
        raise RuntimeError("GNU Make gnulib branch reference changed; audit before updating")
    path.write_text(text.replace(old, "GNULIB_REVISION=" + GNULIB_COMMIT), encoding="utf-8")


def marker_text(revision, seed_make, automake, aclocal, autoconf, autom4te,
                autoreconf, cc, sed, git, autopoint, pkg_config):
    return (
        f"MAKE_BOOTSTRAP_SCHEMA={MAKE_BOOTSTRAP_SCHEMA}\n"
        f"MAKE_GIT_COMMIT={revision}\n"
        f"GNULIB_COMMIT={GNULIB_COMMIT}\n"
        f"SEED_MAKE={seed_make}: {first_line([seed_make, '--version'])}\n"
        f"AUTOMAKE={automake}: {first_line([automake, '--version'])}\n"
        f"ACLOCAL={aclocal}: {first_line([aclocal, '--version'])}\n"
        f"AUTOCONF={autoconf}: {first_line([autoconf, '--version'])}\n"
        f"AUTOM4TE={autom4te}: {first_line([autom4te, '--version'])}\n"
        f"AUTORECONF={autoreconf}: {first_line([autoreconf, '--version'])}\n"
        f"CC={cc}: {first_line([cc, '--version'])}\n"
        f"SED={sed}\n"
        f"GIT={git}: {first_line([git, '--version'])}\n"
        f"AUTOPOINT={autopoint}: {first_line([autopoint, '--version'])}\n"
        f"PKG_CONFIG={pkg_config}: {first_line([pkg_config, '--version'])}\n"
        "PROFILE=tool-only-no-nls-no-guile\n"
    )


def bootstrap(build_root):
    revision = ensure_source()
    seed_make = select_seed_make()
    automake, aclocal = select_automake_pair()
    autoconf, autom4te, autoreconf = select_autoconf_suite()
    cc = select_cc()
    sed = select_seed_sed()
    git = tool("git")
    autopoint = tool("autopoint", "AUTOPOINT")
    pkg_config = tool("pkg-config", "PKG_CONFIG", ("pkgconf",))

    prefix = build_root / "deps" / "make"
    work = build_root / "bootstrap" / "make"
    source = work / "source"
    objects = work / "build"
    marker_path = prefix / ".whp-make-bootstrap"
    marker = marker_text(
        revision, seed_make, automake, aclocal, autoconf, autom4te,
        autoreconf, cc, sed, git, autopoint, pkg_config,
    )
    if marker_path.is_file() and marker_path.read_text(encoding="utf-8") == marker and gnu_make_usable(prefix / "bin" / "make"):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, source)
    pin_gnulib(source)
    objects.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in ("BASH_ENV", "ENV", "POSIXLY_CORRECT", "MAKEFLAGS", "MFLAGS", "MAKELEVEL"):
        env.pop(key, None)
    env.update({
        "MAKE": seed_make,
        "MAKE_CMD": seed_make,
        "CC": cc,
        "AUTOMAKE": automake,
        "ACLOCAL": aclocal,
        "AUTOCONF": autoconf,
        "AUTOM4TE": autom4te,
        "AUTORECONF": autoreconf,
        "AUTOPOINT": autopoint,
        "PKG_CONFIG": pkg_config,
        "SED": sed,
        "GNULIB_URL": GNULIB_URL,
        "MAKEINFO": "true",
    })
    env["PATH"] = os.pathsep.join([
        str(pathlib.Path(automake).parent),
        str(pathlib.Path(autoconf).parent),
        str(pathlib.Path(autopoint).parent),
        str(pathlib.Path(pkg_config).parent),
        env.get("PATH", ""),
    ])

    config_shell = explicit_tool("CONFIG_SHELL") or "/bin/sh"
    print(
        f"WHP GNU Make bootstrap: {revision} -> {prefix} "
        f"(seed {seed_make}, gnulib {GNULIB_COMMIT})",
        file=sys.stderr,
    )
    run_logged(
        [config_shell, str(source / "bootstrap"), "--skip-po", "--force", "--no-bootstrap-sync"],
        cwd=source, env=env,
    )
    configure = source / "configure"
    if not configure.is_file():
        raise RuntimeError("GNU Make bootstrap did not generate configure")
    run_logged(
        [config_shell, str(configure), f"--prefix={prefix}", "--disable-nls", "--without-guile"],
        cwd=objects, env=env,
    )
    run_logged([config_shell, str(source / "build.sh")], cwd=objects, env=env)

    built = objects / "make"
    if not gnu_make_usable(built):
        raise RuntimeError("GNU Make build.sh did not produce a usable binary")

    bindir = prefix / "bin"
    bindir.mkdir(parents=True, exist_ok=True)
    installed = bindir / "make"
    shutil.copy2(built, installed)
    installed.chmod(installed.stat().st_mode | 0o111)
    gmake = bindir / "gmake"
    try:
        gmake.symlink_to("make")
    except OSError:
        shutil.copy2(installed, gmake)
        gmake.chmod(gmake.stat().st_mode | 0o111)

    marker_path.write_text(marker, encoding="utf-8")
    return prefix


def main(argv):
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args(argv)
    try:
        prefix = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP GNU Make bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
