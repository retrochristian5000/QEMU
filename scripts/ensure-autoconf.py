#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned WHP GNU Autoconf as a private host tool.

Autoconf's Git bootstrap self-hosts Autoconf from the source tree, so this
stage deliberately consumes Automake/aclocal, GNU M4, Perl, GNU Make, and the
validated sed seed without consuming an installed Autoconf. The QEMU profile
builds and installs only the executable/library data needed by downstream
Autotools consumers; documentation generation is excluded.
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
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import reconcile_submodule
from bootstrap_env import (clean_host_environment, select_native_cc,
                           select_native_sdk, select_bootstrap_cflags,
                           select_bootstrap_ldflags)
SUBMODULE_REL = pathlib.Path("toolchains/autoconf")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SED_ADAPTER = ROOT / "seeds" / "sed.sh"
AUTOCONF_BOOTSTRAP_SCHEMA = "7"

# Installed scripts to inspect individually before using or caching a prefix.
# A successful install target does not prove every executable was installed.
REQUIRED_BINARIES = (
    "autoconf", "autom4te", "autoheader", "autoreconf",
    "autoscan", "autoupdate", "ifnames",
)

BUILD_TARGETS = (
    "bin/autoconf",
    "bin/autoheader",
    "bin/autom4te",
    "bin/autoreconf",
    "bin/autoscan",
    "bin/autoupdate",
    "bin/ifnames",
    "lib/autom4te.cfg",
    "lib/autoconf/autoconf.m4f",
    "lib/autoscan/autoscan.list",
    "lib/m4sugar/m4sugar.m4f",
    "lib/m4sugar/m4sh.m4f",
    "lib/autotest/autotest.m4f",
)

# Automake keeps dist_/nodist_ in the generated rule name even though both
# install into the same logical directory.  Name the generated rules exactly;
# asking for collapsed names such as install-perllibDATA is not portable and
# currently fails with the managed Automake tree.
INSTALL_TARGETS = (
    "install-binSCRIPTS",
    "install-dist_perllibDATA",
    "install-nodist_pkgdataDATA",
    "install-dist_autoconflibDATA",
    "install-nodist_autoconflibDATA",
    "install-nodist_autoscanlibDATA",
    "install-dist_m4sugarlibDATA",
    "install-nodist_m4sugarlibDATA",
    "install-dist_autotestlibDATA",
    "install-nodist_autotestlibDATA",
    "install-dist_buildauxDATA",
    "install-data-hook",
)


def run_text(
    command: list[str],
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
    command: list[str],
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


def explicit_tool(env_name: str) -> str | None:
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


def tool(name: str, env_name: str | None = None, aliases: tuple[str, ...] = ()) -> str:
    requested = explicit_tool(env_name) if env_name else None
    if requested:
        return requested
    for candidate in (name, *aliases):
        path = executable(candidate)
        if path:
            return path
    raise RuntimeError(f"{name} is required to bootstrap GNU Autoconf")


def first_line(command: list[str]) -> str:
    # Perl and some compiler version banners start with an empty line.
    # Recording that blank line makes the cache marker insensitive to
    # version changes at an unchanged executable path.
    for line in run_text(command, env=clean_host_environment(os.environ)).splitlines():
        if line.strip():
            return line.strip()
    raise RuntimeError(f"version command returned no text: {shlex.join(command)}")


def select_seed_perl() -> str:
    # A native Perl is required by source generation. Validate it once
    # through the same seed adapter instead of trusting a path-only probe.
    adapter = ROOT / "seeds" / "perl.sh"
    if not adapter.is_file():
        raise RuntimeError(f"QEMU Perl seed is unavailable: {adapter}")
    completed = subprocess.run(
        ["/bin/sh", str(adapter), "--print-autotools-seed"],
        env=clean_host_environment(os.environ),
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    selected = completed.stdout.strip()
    if completed.returncode != 0 or not selected:
        raise RuntimeError(
            "Autotools bootstrap requires Perl with its runtime modules: "
            + (completed.stderr.strip() or "Perl >= 5.6 is unavailable")
        )
    return selected


def select_gnu_make() -> str:
    requested = explicit_tool("MAKE_CMD") or explicit_tool("MAKE")
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
    raise RuntimeError("GNU Make is required to bootstrap GNU Autoconf")


def gnu_m4_version(path: str) -> str:
    completed = subprocess.run(
        [path, "--gnu", "--version"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    output = completed.stdout.strip()
    first = output.splitlines()[0] if output else "<no version output>"
    if completed.returncode != 0 or "GNU M4" not in output:
        raise RuntimeError(
            f"not GNU M4 with --gnu support: {path}: {first}"
        )

    # Autoconf's maintainer bootstrap deliberately rejects the historical
    # 1.4.11-1.4.15 strstr bugs. Enforce that boundary before entering the
    # source bootstrap so macOS failures identify M4 directly.
    match = re.search(r"(?<![0-9])([0-9]+)\.([0-9]+)(?:\.([0-9]+))?", first)
    if not match:
        raise RuntimeError(f"could not parse GNU M4 version: {path}: {first}")
    version = tuple(int(piece or "0") for piece in match.groups())
    if version < (1, 4, 16):
        raise RuntimeError(
            "GNU M4 1.4.16 or newer is required to bootstrap Autoconf: "
            f"{path}: {first}"
        )

    # A version banner alone does not prove that the binary can execute
    # GNU extensions.  Exercise a GNU-only macro before Autoconf embeds
    # this path in autom4te and passes it to subsequent bootstrap stages.
    probe = subprocess.run(
        [path, "--gnu", "--fatal-warnings"],
        input="patsubst(`ab12cd', `[0-9]+', `X')\n",
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if probe.returncode != 0 or probe.stdout.strip() != "abXcd":
        detail = (
            probe.stderr.strip()
            or probe.stdout.strip()
            or f"exit status {probe.returncode}"
        )
        raise RuntimeError(f"GNU M4 macro expansion failed: {path}: {detail}")
    return first


def select_gnu_m4() -> str:
    # One validated GNU M4 selection for all maintainer-source consumers.
    # The seed checks the Autoconf 1.4.16 floor and GNU macro execution,
    # including explicitly requested M4/WHP_M4_SEED implementations.
    adapter = ROOT / "seeds" / "gnum4.sh"
    if not adapter.is_file():
        raise RuntimeError(f"QEMU GNU M4 seed is unavailable: {adapter}")
    completed = subprocess.run(
        ["/bin/sh", str(adapter), "--print-seed"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    selected = completed.stdout.strip()
    if completed.returncode or not selected:
        raise RuntimeError(
            "GNU M4 selection failed: "
            + (completed.stderr.strip() or "no usable GNU M4")
        )
    return selected

def select_automake_pair() -> tuple[str, str]:
    # Resolve both tools through the same seed. PATH may contain a different
    # aclocal release from the Automake selected by the caller.
    adapter = ROOT / "seeds" / "automake.sh"
    if not adapter.is_file():
        raise RuntimeError(f"QEMU Automake seed adapter is unavailable: {adapter}")
    selected = []
    for flag in ("--print-seed", "--print-aclocal"):
        completed = subprocess.run(
            ["/bin/sh", str(adapter), flag],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        path = completed.stdout.strip()
        if completed.returncode or not path:
            raise RuntimeError(
                "QEMU Automake/aclocal seed resolution failed: "
                + (completed.stderr.strip() or flag)
            )
        selected.append(path)
    return selected[0], selected[1]


def select_seed_sed() -> str:
    if not SED_ADAPTER.is_file() or not os.access(SED_ADAPTER, os.X_OK):
        raise RuntimeError(f"QEMU sed seed adapter is unavailable: {SED_ADAPTER}")
    env = os.environ.copy()
    requested = os.environ.get("WHP_SED_SEED", "")
    if requested:
        env["WHP_SED_SEED"] = requested
    completed = subprocess.run(
        [str(SED_ADAPTER), "--print-seed"],
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    seed = completed.stdout.strip()
    if completed.returncode != 0 or not seed:
        detail = completed.stderr.strip()
        raise RuntimeError(
            "QEMU sed.sh could not resolve the Autoconf bootstrap seed"
            + (f": {detail}" if detail else "")
        )
    return seed


def select_seed_ln() -> str:
    """Admit the same native ln implementation used by the QEMU root build."""
    adapter = ROOT / "seeds" / "ln.sh"
    if not adapter.is_file():
        raise RuntimeError(f"QEMU ln seed adapter is missing: {adapter}")
    completed = subprocess.run(
        ["/bin/sh", str(adapter), "--print-seed"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    path = completed.stdout.strip()
    if (
        completed.returncode != 0
        or not path
        or "\n" in path
        or not pathlib.Path(path).is_absolute()
        or not pathlib.Path(path).is_file()
        or not os.access(path, os.X_OK)
    ):
        raise RuntimeError(
            "QEMU ln seed handshake failed: "
            + (completed.stderr.strip() or path or "no usable native ln")
        )
    return path


def select_bootstrap_text_tool(name: str) -> str:
    """Resolve validated host AWK or grep after optional Gawk promotion."""
    if name not in ("awk", "grep"):
        raise ValueError(f"unsupported Autoconf text-tool seed: {name}")
    adapter = ROOT / "seeds" / f"{name}.sh"
    if not adapter.is_file():
        raise RuntimeError(f"QEMU {name} seed adapter is missing: {adapter}")
    result = subprocess.run(
        ["/bin/sh", str(adapter), "--print-seed"],
        text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    path = result.stdout.strip()
    if (
        result.returncode != 0
        or not path
        or "\n" in path
        or not pathlib.Path(path).is_absolute()
        or not pathlib.Path(path).is_file()
        or not os.access(path, os.X_OK)
    ):
        raise RuntimeError(
            f"QEMU {name} seed handshake failed: "
            + (result.stderr.strip() or path or "no selected executable")
        )
    return path


def select_bootstrap_git() -> str | None:
    """Reuse QEMU seed Git for submodule reconciliation and source archives."""
    if not (ROOT / ".git").exists():
        return None
    selected = os.environ.get("WHP_GIT_SEED", "")
    if selected:
        path = executable(selected)
        if not path:
            raise RuntimeError(f"WHP_GIT_SEED is not executable: {selected}")
        if not run_text([path, "--version"]).startswith("git version "):
            raise RuntimeError(f"WHP_GIT_SEED is not Git: {selected}")
        return path
    adapter = ROOT / "seeds" / "git.sh"
    result = subprocess.run(
        ["/bin/sh", str(adapter), "--print-seed"], text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
    )
    path = result.stdout.strip()
    if result.returncode or not path:
        raise RuntimeError("Autoconf requires a validated Git seed: "
                           + (result.stderr.strip() or "unavailable"))
    return path


def archive_source_signature() -> str:
    # Without a Git ref, hash the source inputs rather than only bootstrap
    # entrypoints. A changed M4 macro or Perl library must invalidate reuse.
    required = (
        "bootstrap", "configure.ac", "Makefile.am",
        "bin/autoconf.in", "bin/autom4te.in",
    )
    for name in required:
        if not (SUBMODULE_DIR / name).is_file():
            raise RuntimeError(
                f"bundled Autoconf source is unavailable: {SUBMODULE_DIR / name}"
            )

    candidates = {SUBMODULE_DIR / name for name in required}
    candidates.update(
        path for path in SUBMODULE_DIR.iterdir()
        if path.is_file() and (
            path.suffix in (".am", ".ac", ".mk")
            or path.name == "GNUmakefile"
        )
    )
    # All five local.mk fragments are included by Makefile.am. A change in
    # any of them can alter generated build rules, even if a minimal install
    # does not request that fragment's documentation or test targets.
    for directory in ("bin", "lib", "m4", "build-aux",
                      "doc", "man", "tests"):
        folder = SUBMODULE_DIR / directory
        if not folder.is_dir():
            continue
        candidates.update(
            path for path in folder.rglob("*")
            if path.is_file() and path.suffix in (
                ".m4", ".pm", ".pl", ".in", ".am", ".mk"
            )
        )
    # Generated .m4f, cache files and transient configure scripts are
    # intentionally excluded: touching them must not force a source rebuild.
    digest = hashlib.sha256()
    for path in sorted(candidates):
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "archive-" + digest.hexdigest()


def ensure_source(git: str | None) -> str:
    if git is None:
        return archive_source_signature()
    return reconcile_submodule(ROOT, SUBMODULE_REL, git=git)


def extract_git_archive(
    repo: pathlib.Path, revision: str, destination: pathlib.Path, git: str
) -> None:
    completed = subprocess.run(
        [git, "-C", str(repo), "archive", "--format=tar", revision],
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
    news = (SUBMODULE_DIR / "NEWS").read_text(encoding="utf-8", errors="replace")
    match = re.search(
        r"(?m)^\* Noteworthy changes in release ([0-9]+(?:\.[0-9]+)+) \(",
        news,
    )
    return match.group(1) if match else "0"


def staged_version(revision: str) -> str:
    base = latest_release_version()
    if revision.startswith("archive-"):
        kind = "archive"
        identity = revision.removeprefix("archive-")[:12]
    else:
        kind = "git"
        identity = revision[:12]
    identity = re.sub(r"[^0-9A-Za-z]+", "", identity) or "unknown"
    return f"{base}.{kind}-{identity}"


def copy_source(revision: str, destination: pathlib.Path, git: str | None) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    if git is not None and (SUBMODULE_DIR / ".git").exists():
        extract_git_archive(SUBMODULE_DIR, revision, destination, git)
    else:
        shutil.copytree(
            SUBMODULE_DIR,
            destination,
            ignore=shutil.ignore_patterns(".git"),
        )
    (destination / ".tarball-version").write_text(
        staged_version(revision) + "\n", encoding="utf-8"
    )


def suite_usable(prefix: pathlib.Path, *, m4: str | None = None) -> bool:
    for name in REQUIRED_BINARIES:
        path = prefix / "bin" / name
        if not path.is_file() or not os.access(path, os.X_OK):
            print(f"WHP Autoconf runtime: missing executable {path}", file=sys.stderr)
            return False
        completed = subprocess.run(
            [str(path), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0 or "GNU Autoconf" not in completed.stdout:
            banner = completed.stdout.splitlines()
            detail = banner[0] if banner else "<no version output>"
            print(
                f"WHP Autoconf runtime: {path} --version failed "
                f"(exit {completed.returncode}; {detail})",
                file=sys.stderr,
            )
            return False

    # --version does not load Autom4te's Perl modules or the installed M4
    # libraries.  The bootstrap callers deliberately poison AUTOCONF/AUTOM4TE
    # to prove self-host isolation, so do not let those seed-only sentinels
    # leak into validation of the completed private installation.
    smoke_env = clean_host_environment(os.environ)
    for key in ("AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF", "M4"):
        smoke_env.pop(key, None)
    if m4 is not None:
        # A poisoned caller M4 must not make validation fall back to PATH.
        smoke_env["M4"] = m4

    with tempfile.TemporaryDirectory(prefix="whp-autoconf-smoke-") as tmp:
        smoke_dir = pathlib.Path(tmp)
        configure_ac = smoke_dir / "configure.ac"
        configure_ac.write_text(
            "AC_INIT([whp-bootstrap-smoke],[1])\nAC_OUTPUT\n",
            encoding="utf-8",
        )
        completed = subprocess.run(
            [str(prefix / "bin" / "autoconf")],
            cwd=smoke_dir,
            env=smoke_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        configure = smoke_dir / "configure"
        if completed.returncode == 0 and configure.is_file():
            return True

        detail = completed.stderr.strip() or completed.stdout.strip()
        print(
            "WHP Autoconf installed-runtime smoke failed"
            + (f": {detail}" if detail else ""),
            file=sys.stderr,
        )
        return False


def marker_text(
    revision: str,
    automake: str,
    aclocal: str,
    m4: str,
    perl: str,
    make: str,
    seed: str,
    awk: str,
    grep: str,
    ln: str,
    cc: str,
    config_shell: str,
) -> str:
    return (
        f"AUTOCONF_BOOTSTRAP_SCHEMA={AUTOCONF_BOOTSTRAP_SCHEMA}\n"
        f"AUTOCONF_GIT_COMMIT={revision}\n"
        f"AUTOMAKE={automake}: {first_line([automake, '--version'])}\n"
        f"ACLOCAL={aclocal}: {first_line([aclocal, '--version'])}\n"
        f"M4_PATH={m4}\n"
        f"M4_VERSION={gnu_m4_version(m4)}\n"
        f"PERL={perl}: {first_line([perl, '--version'])}\n"
        f"MAKE={make}: {first_line([make, '--version'])}\n"
        f"SEED_SED={seed}\n"
        f"AWK={awk}\n"
        f"GREP={grep}\n"
        f"LN={ln}\n"
        f"CC_FOR_BUILD={cc}: {first_line([cc, '--version'])}\n"
        f"CONFIG_SHELL={config_shell}\n"
        f"SDKROOT={os.environ.get('SDKROOT', '')}\n"
        f"MACOSX_DEPLOYMENT_TARGET={os.environ.get('MACOSX_DEPLOYMENT_TARGET', '')}\n"
        "PROFILE=tool-only-no-docs\n"
    )


def restore_previous_install(prefix: pathlib.Path, backup: pathlib.Path) -> None:
    """Recover the previous installation after an interrupted rebuild."""
    if not backup.exists():
        return
    if prefix.exists():
        shutil.rmtree(prefix)
    backup.rename(prefix)


def parallel_jobs(value: str | None) -> int:
    """Validate explicit job counts before moving any installed prefix."""
    if value is None or value == "":
        return max(1, os.cpu_count() or 1)
    if not value.isdecimal() or int(value) < 1:
        raise RuntimeError(f"JOBS must be a positive integer, got {value!r}")
    return int(value)


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    # Validate seeds before source fetch or archive extraction.
    automake, aclocal = select_automake_pair()
    m4 = select_gnu_m4()
    perl = select_seed_perl()
    make = select_gnu_make()
    seed = select_seed_sed()
    awk = select_bootstrap_text_tool("awk")
    grep = select_bootstrap_text_tool("grep")
    sdkroot = select_native_sdk(ROOT)
    if sdkroot:
        # cc.sh validates the same SDK; configure must receive it as well.
        os.environ["SDKROOT"] = sdkroot
    cc = select_native_cc(ROOT)
    bootstrap_cflags = select_bootstrap_cflags("autoconf", cc)
    bootstrap_ldflags = select_bootstrap_ldflags(
        "autoconf", cc, cflags=bootstrap_cflags
    )
    config_shell = explicit_tool("CONFIG_SHELL") or "/bin/sh"
    jobs = parallel_jobs(os.environ.get("JOBS"))
    # The pinned source bootstrap actually invokes mktemp. It does not
    # invoke the standalone realpath command: Python's pathlib resolves
    # our paths already. Do not reject a native host merely for lacking
    # GNU coreutils realpath (not present on some older macOS systems).
    tool("mktemp")
    # bin/local.mk chmods generated scripts; lib/local.mk sorts autoscan.list.
    # Unlike help2man and makeinfo, these run for BUILD_TARGETS below.
    for name in ("chmod", "sort"):
        tool(name)
    ln = select_seed_ln()
    git = select_bootstrap_git()
    revision = ensure_source(git)

    prefix = build_root / "deps" / "autoconf"
    work = build_root / "bootstrap" / "autoconf"
    source = work / "source"
    objects = work / "build"
    marker_path = prefix / ".whp-autoconf-bootstrap"
    backup = build_root / "bootstrap" / "autoconf-previous-install"

    marker = marker_text(
        revision, automake, aclocal, m4, perl, make, seed, awk, grep, ln, cc,
        config_shell
    )
    if bootstrap_cflags:
        marker += f"BOOTSTRAP_CFLAGS={bootstrap_cflags}\n"
    if bootstrap_ldflags:
        marker += f"BOOTSTRAP_LDFLAGS={bootstrap_ldflags}\n"
    # Recover from a prior interrupted rebuild. A completed replacement
    # is kept only if its marker and installed runtime both validate.
    if backup.exists():
        if (
            marker_path.is_file()
            and marker_path.read_text(encoding="utf-8", errors="replace") == marker
            and suite_usable(prefix, m4=m4)
        ):
            shutil.rmtree(backup)
            return prefix
        restore_previous_install(prefix, backup)

    if (
        marker_path.is_file()
        and marker_path.read_text(encoding="utf-8", errors="replace") == marker
        and suite_usable(prefix, m4=m4)
    ):
        return prefix

    # Prepare sources without destroying the previous installed suite.
    shutil.rmtree(work, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, source, git)
    objects.mkdir(parents=True, exist_ok=True)

    seed_bin = work / "seed-bin"
    seed_bin.mkdir(parents=True, exist_ok=True)
    seed_link = seed_bin / "sed"
    try:
        seed_link.symlink_to(SED_ADAPTER)
    except OSError:
        shutil.copy2(SED_ADAPTER, seed_link)
        seed_link.chmod(seed_link.stat().st_mode | 0o111)

    # Match literal awk/grep commands to the selected $AWK/$GREP providers.
    for name, selected in (("awk", awk), ("grep", grep)):
        link = seed_bin / name
        try:
            link.symlink_to(selected)
        except OSError:
            shutil.copy2(selected, link)
            link.chmod(link.stat().st_mode | 0o111)

    # The pinned source uses LN_S="ln -s". Bind that literal command to the
    # validated native seed, not to an unrelated PATH implementation.
    ln_link = seed_bin / "ln"
    try:
        ln_link.symlink_to(ln)
    except OSError:
        shutil.copy2(ln, ln_link)
        ln_link.chmod(ln_link.stat().st_mode | 0o111)

    # Some Autotools helpers still invoke literal "m4" even when M4 is set.
    # Mirror the validated executable under that canonical name so PATH and the
    # M4 variable always resolve to the same implementation.
    m4_link = seed_bin / "m4"
    try:
        m4_link.symlink_to(m4)
    except OSError:
        shutil.copy2(m4, m4_link)
        m4_link.chmod(m4_link.stat().st_mode | 0o111)

    env = clean_host_environment(os.environ)
    env["CC"] = cc
    if bootstrap_cflags:
        env["CFLAGS"] = bootstrap_cflags
    if bootstrap_ldflags:
        env["LDFLAGS"] = bootstrap_ldflags
    env["CC_FOR_BUILD"] = cc
    env["MAKE"] = make
    env["MAKE_CMD"] = make
    env["CONFIG_SHELL"] = config_shell
    env["SHELL"] = config_shell
    # Never consume a partially bootstrapped Autoconf executable.
    for key in ("AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF",
                "MAKEINFO", "HELP2MAN"):
        env.pop(key, None)
    env["AUTOMAKE"] = automake
    env["ACLOCAL"] = aclocal
    env["M4"] = m4
    env["LN_S"] = "ln -s"
    env["PERL"] = perl
    env["AWK"] = awk
    env["GREP"] = grep
    env["WHP_AWK_SEED"] = awk
    env["WHP_GREP_SEED"] = grep
    env["WHP_SED_SEED"] = seed
    # Route both $SED and literal sed through one traceable bootstrap adapter.
    env["SED"] = str(SED_ADAPTER)
    env["EMACS"] = "no"
    env["PATH"] = (
        str(seed_bin)
        + os.pathsep
        + str(pathlib.Path(automake).parent)
        + os.pathsep
        + env.get("PATH", "")
    )

    print(
        f"WHP Autoconf bootstrap: {revision} -> {prefix} "
        f"(Automake {automake}, GNU M4 {m4}, seed sed {seed}, "
        f"AWK {awk}, grep {grep})",
        file=sys.stderr,
    )

    # Installed Autoconf scripts embed this final prefix. A staging-prefix
    # install followed by a rename would invalidate those embedded paths.
    if prefix.exists():
        prefix.rename(backup)
    try:
        run_logged([config_shell, str(source / "bootstrap")], cwd=source, env=env)
        configure = source / "configure"
        if not configure.is_file():
            raise RuntimeError("Autoconf bootstrap did not generate configure")

        run_logged(
            [config_shell, str(configure), f"--prefix={prefix}"],
            cwd=objects,
            env=env,
        )
        run_logged(
            [make, "-j", str(jobs), *BUILD_TARGETS],
            cwd=objects,
            env=env,
        )
        run_logged(
            [make, *INSTALL_TARGETS, "pkgdata_DATA="],
            cwd=objects,
            env=env,
        )

        if not suite_usable(prefix, m4=m4):
            raise RuntimeError(
                f"bootstrapped Autoconf tool suite is not usable: {prefix}"
            )
        marker_path.write_text(marker, encoding="utf-8")
    except (OSError, RuntimeError, subprocess.SubprocessError):
        if backup.exists():
            restore_previous_install(prefix, backup)
            print("WHP Autoconf: restored previous installation", file=sys.stderr)
        else:
            shutil.rmtree(prefix, ignore_errors=True)
        raise

    if backup.exists():
        shutil.rmtree(backup)
    return prefix


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build-dir", required=True)
    args = parser.parse_args(argv)
    try:
        prefix = bootstrap(pathlib.Path(args.build_dir).expanduser().resolve())
    except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
        print(f"error: WHP Autoconf bootstrap failed: {exc}", file=sys.stderr)
        return 1
    print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
