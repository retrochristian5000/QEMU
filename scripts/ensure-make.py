#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP GNU Make as a managed host tool."""

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

ROOT = pathlib.Path(__file__).resolve().parents[1]
SUBMODULE_REL = pathlib.Path("toolchains/make")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SED_ADAPTER = ROOT / "sed.sh"

MAKE_BOOTSTRAP_SCHEMA = "3"
GNULIB_COMMIT = "b22f5a3037712a3c957a03071ce0b219cef4d65b"
GNULIB_URL = "https://github.com/coreutils/gnulib.git"

MAKE_CONFIGURE_ARGS = (
    "--disable-dependency-tracking",
    "--disable-nls",
    "--without-guile",
)


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


def autoconf_version(path):
    line = first_line([path, "--version"])
    match = re.search(r"([0-9]+(?:\\.[0-9]+)+)(?:[^0-9].*)?$", line)
    if "GNU Autoconf" not in line or not match:
        raise RuntimeError(f"not a usable GNU Autoconf tool: {path}: {line}")
    return match.group(1)


def select_autoconf_suite():
    autoconf = explicit_tool("AUTOCONF") or executable("autoconf")
    if not autoconf:
        raise RuntimeError("Autoconf is required to bootstrap GNU Make")

    suite_dir = pathlib.Path(autoconf).parent

    def companion(name, env_name):
        requested = explicit_tool(env_name)
        if requested:
            return requested
        local = executable(str(suite_dir / name))
        return local or executable(name)

    autom4te = companion("autom4te", "AUTOM4TE")
    autoheader = companion("autoheader", "AUTOHEADER")
    autoreconf = companion("autoreconf", "AUTORECONF")
    if not autom4te or not autoheader or not autoreconf:
        raise RuntimeError(
            "Autoconf/autom4te/autoheader/autoreconf are required "
            "to bootstrap GNU Make"
        )

    suite = (autoconf, autom4te, autoheader, autoreconf)
    versions = {autoconf_version(path) for path in suite}
    if len(versions) != 1:
        detail = ", ".join(
            f"{path}={autoconf_version(path)}" for path in suite
        )
        raise RuntimeError(f"mixed GNU Autoconf tool suite: {detail}")

    return autoconf, autom4te, autoheader, autoreconf


def shell_usable(path):
    completed = subprocess.run(
        [path, "-c", "exit 0"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return completed.returncode == 0


def resolve_shell(requested, env_name):
    argv = shlex.split(requested)
    if len(argv) != 1:
        raise RuntimeError(f"{env_name} must name exactly one executable")
    path = executable(argv[0])
    if not path or not shell_usable(path):
        raise RuntimeError(f"{env_name} is not a usable shell: {argv[0]}")
    return path


def select_config_shell():
    for env_name in ("WHP_BUILD_BASH", "CONFIG_SHELL"):
        requested = os.environ.get(env_name, "")
        if requested:
            return resolve_shell(requested, env_name)
    if pathlib.Path("/bin/sh").is_file() and shell_usable("/bin/sh"):
        return "/bin/sh"
    path = executable("sh")
    if path and shell_usable(path):
        return path
    raise RuntimeError("a usable configuration shell is required to bootstrap GNU Make")


def shell_identity(path):
    completed = subprocess.run(
        [path, "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    first = completed.stdout.splitlines()[0] if completed.stdout else ""
    return f"{path}|{first}"


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


def gnulib_cache_usable(path, git):
    if not (path / ".git").exists() or not (path / "gnulib-tool").is_file():
        return False
    try:
        head = run_text([git, "-C", str(path), "rev-parse", "HEAD"])
        dirty = run_text([
            git, "-C", str(path), "status", "--porcelain",
            "--untracked-files=no",
        ])
    except RuntimeError:
        return False
    return head == GNULIB_COMMIT and not dirty


def ensure_gnulib_cache(build_root, git):
    cache = build_root / "cache" / "gnulib" / GNULIB_COMMIT
    if gnulib_cache_usable(cache, git):
        print(f"WHP GNU Make gnulib cache: reused {cache}", file=sys.stderr)
        return cache

    cache.parent.mkdir(parents=True, exist_ok=True)
    staging = cache.parent / f".{GNULIB_COMMIT}.new.{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)

    try:
        run_logged([git, "init", str(staging)])
        run_logged([git, "-C", str(staging), "remote", "add", "origin", GNULIB_URL])

        fetched = subprocess.run(
            [git, "-C", str(staging), "fetch", "--depth", "1",
             "origin", GNULIB_COMMIT],
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
        )
        if fetched.returncode == 0:
            run_logged([
                git, "-C", str(staging), "checkout", "--detach", "FETCH_HEAD",
            ])
        else:
            # Some Git servers do not allow a shallow fetch by raw commit.
            # Fall back to the remote history only when that capability is
            # unavailable, then detach at the exact pinned commit.
            run_logged([git, "-C", str(staging), "fetch", "origin"])
            run_logged([
                git, "-C", str(staging), "checkout", "--detach", GNULIB_COMMIT,
            ])

        if not gnulib_cache_usable(staging, git):
            raise RuntimeError(
                f"downloaded gnulib cache is not pinned at {GNULIB_COMMIT}"
            )

        # Another bootstrap may have populated the same immutable cache while
        # this process was fetching. Prefer a valid existing copy.
        if gnulib_cache_usable(cache, git):
            shutil.rmtree(staging, ignore_errors=True)
            print(f"WHP GNU Make gnulib cache: reused {cache}", file=sys.stderr)
            return cache

        shutil.rmtree(cache, ignore_errors=True)
        os.replace(staging, cache)
    except BaseException:
        shutil.rmtree(staging, ignore_errors=True)
        raise

    print(f"WHP GNU Make gnulib cache: populated {cache}", file=sys.stderr)
    return cache


def marker_text(revision, seed_make, automake, aclocal, autoconf, autom4te,
                autoheader, autoreconf, cc, sed, git, autopoint, pkg_config,
                config_shell):
    return (
        f"MAKE_BOOTSTRAP_SCHEMA={MAKE_BOOTSTRAP_SCHEMA}\n"
        f"MAKE_GIT_COMMIT={revision}\n"
        f"GNULIB_COMMIT={GNULIB_COMMIT}\n"
        f"HOST_SYSTEM={platform.system()}\n"
        f"HOST_MACHINE={platform.machine()}\n"
        f"SEED_MAKE={seed_make}: {first_line([seed_make, '--version'])}\n"
        f"AUTOMAKE={automake}: {first_line([automake, '--version'])}\n"
        f"ACLOCAL={aclocal}: {first_line([aclocal, '--version'])}\n"
        f"AUTOCONF={autoconf}: {first_line([autoconf, '--version'])}\n"
        f"AUTOM4TE={autom4te}: {first_line([autom4te, '--version'])}\n"
        f"AUTOHEADER={autoheader}: {first_line([autoheader, '--version'])}\n"
        f"AUTORECONF={autoreconf}: {first_line([autoreconf, '--version'])}\n"
        f"CONFIG_SHELL={shell_identity(config_shell)}\n"
        f"CC={cc}: {first_line([cc, '--version'])}\n"
        f"SED={sed}\n"
        f"GIT={git}: {first_line([git, '--version'])}\n"
        f"AUTOPOINT={autopoint}: {first_line([autopoint, '--version'])}\n"
        f"PKG_CONFIG={pkg_config}: {first_line([pkg_config, '--version'])}\n"
        f"ACLOCAL_PATH={os.environ.get('ACLOCAL_PATH', '')}\n"
        f"CONFIGURE_ARGS={shlex.join(MAKE_CONFIGURE_ARGS)}\n"
        "PROFILE=tool-only-no-nls-no-guile\n"
    )


def bootstrap(build_root):
    revision = ensure_source()
    seed_make = select_seed_make()
    automake, aclocal = select_automake_pair()
    autoconf, autom4te, autoheader, autoreconf = select_autoconf_suite()
    cc = select_cc()
    sed = select_seed_sed()
    git = tool("git")
    autopoint = tool("autopoint", "AUTOPOINT")
    pkg_config = tool("pkg-config", "PKG_CONFIG", ("pkgconf",))
    config_shell = select_config_shell()

    prefix = build_root / "deps" / "make"
    work = build_root / "bootstrap" / "make"
    source = work / "source"
    objects = work / "build"
    marker_path = prefix / ".whp-make-bootstrap"
    marker = marker_text(
        revision, seed_make, automake, aclocal, autoconf, autom4te,
        autoheader, autoreconf, cc, sed, git, autopoint, pkg_config,
        config_shell,
    )
    if marker_path.is_file() and marker_path.read_text(encoding="utf-8") == marker and gnu_make_usable(prefix / "bin" / "make"):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, source)
    pin_gnulib(source)
    gnulib_source = ensure_gnulib_cache(build_root, git)
    objects.mkdir(parents=True, exist_ok=True)

    env = os.environ.copy()
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT",
        "MAKEFLAGS", "MFLAGS", "GNUMAKEFLAGS", "MAKEFILES",
        "MAKEOVERRIDES", "MAKELEVEL",
        "CC", "CXX", "AR", "AS", "LD", "NM", "RANLIB", "STRIP",
        "CFLAGS", "CXXFLAGS", "CPPFLAGS", "LDFLAGS", "OBJCFLAGS",
        "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR",
        "CONFIG_SITE", "M4", "WARNINGS",
    ):
        env.pop(key, None)
    for key in tuple(env):
        if key.startswith(("ac_cv_", "gl_cv_", "make_cv_")):
            env.pop(key, None)

    env.update({
        "MAKE": seed_make,
        "MAKE_CMD": seed_make,
        "CC": cc,
        "AUTOMAKE": automake,
        "ACLOCAL": aclocal,
        "AUTOCONF": autoconf,
        "AUTOM4TE": autom4te,
        "AUTOHEADER": autoheader,
        "AUTORECONF": autoreconf,
        "AUTOPOINT": autopoint,
        "PKG_CONFIG": pkg_config,
        "SED": sed,
        "GNULIB_URL": GNULIB_URL,
        "GNULIB_SRCDIR": str(gnulib_source),
        "CONFIG_SHELL": config_shell,
        "SHELL": config_shell,
        "MAKEINFO": "true",
    })
    env["PATH"] = os.pathsep.join([
        str(pathlib.Path(automake).parent),
        str(pathlib.Path(autoconf).parent),
        str(pathlib.Path(autopoint).parent),
        str(pathlib.Path(pkg_config).parent),
        env.get("PATH", ""),
    ])

    print(
        f"WHP GNU Make bootstrap: {revision} -> {prefix} "
        f"(seed {seed_make}, gnulib {GNULIB_COMMIT})",
        file=sys.stderr,
    )
    run_logged(
        [
            config_shell, str(source / "bootstrap"),
            "--gen", "--no-git", "--skip-po", "--force",
            "--no-bootstrap-sync",
        ],
        cwd=source, env=env,
    )
    configure = source / "configure"
    if not configure.is_file():
        raise RuntimeError("GNU Make bootstrap did not generate configure")
    run_logged(
        [config_shell, str(configure), f"--prefix={prefix}", *MAKE_CONFIGURE_ARGS],
        cwd=objects, env=env,
    )

    configured_outputs = (
        objects / "build.cfg",
        objects / "config.status",
        objects / "Makefile",
        objects / "lib" / "Makefile",
        objects / "src" / "config.h",
        objects / "build.sh",
    )
    missing = [str(path) for path in configured_outputs if not path.is_file()]
    if missing:
        raise RuntimeError(
            "GNU Make configure did not produce required bootstrap files: "
            + ", ".join(missing)
        )

    # configure.ac deliberately AC_CONFIG_LINKS build.sh into the build tree.
    # Consume that configured entry rather than bypassing config.status by
    # reaching back into the staged source tree.
    configured_build = objects / "build.sh"
    run_logged([config_shell, str(configured_build)], cwd=objects, env=env)

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
