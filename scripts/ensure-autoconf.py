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
SUBMODULE_REL = pathlib.Path("toolchains/autoconf")
SUBMODULE_DIR = ROOT / SUBMODULE_REL
SED_ADAPTER = ROOT / "sed.sh"
AUTOCONF_BOOTSTRAP_SCHEMA = "3"

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
    output = run_text(command)
    return output.splitlines()[0] if output else ""


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
    if completed.returncode != 0 or "GNU M4" not in output:
        detail = output.splitlines()[0] if output else "<no version output>"
        raise RuntimeError(
            f"not GNU M4 with --gnu support: {path}: {detail}"
        )
    return output.splitlines()[0]


def select_gnu_m4() -> str:
    requested = explicit_tool("M4")
    if requested:
        gnu_m4_version(requested)
        return requested

    candidates: list[str] = []

    def add_candidate(candidate: str | None) -> None:
        if candidate and candidate not in candidates:
            candidates.append(candidate)

    if platform.system() == "Darwin":
        # Homebrew's GNU M4 is keg-only because macOS already provides M4
        # compatibility tools. Prefer the keg before PATH so /usr/bin/gm4
        # cannot silently become the embedded Autoconf M4 when a managed GNU
        # M4 installation is available.
        for candidate in (
            "/opt/homebrew/opt/m4/bin/m4",
            "/usr/local/opt/m4/bin/m4",
        ):
            add_candidate(executable(candidate))

        brew = executable("brew")
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
                if prefix:
                    add_candidate(
                        executable(str(pathlib.Path(prefix) / "bin" / "m4"))
                    )

    # Prefer the canonical m4 name. gm4 remains a validated seed fallback for
    # hosts where GNU M4 is intentionally installed under that compatibility
    # name, but it no longer wins merely because macOS exposes /usr/bin/gm4.
    for name in ("m4", "gm4"):
        add_candidate(executable(name))

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
        "GNU M4 with --gnu support is required to bootstrap GNU Autoconf: "
        + detail
    )


def select_automake_pair() -> tuple[str, str]:
    automake = explicit_tool("AUTOMAKE") or executable("automake")
    aclocal = explicit_tool("ACLOCAL") or executable("aclocal")
    if not automake or not aclocal:
        raise RuntimeError("Automake/aclocal are required to bootstrap GNU Autoconf")
    for path in (automake, aclocal):
        completed = subprocess.run(
            [path, "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0 or "GNU automake" not in completed.stdout:
            raise RuntimeError(f"not a usable GNU Automake tool: {path}")
    return automake, aclocal


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


def git_checkout_available() -> bool:
    return shutil.which("git") is not None and (ROOT / ".git").exists()


def gitlink_revision() -> str:
    line = run_text([
        "git", "-C", str(ROOT), "ls-tree", "HEAD", "--", str(SUBMODULE_REL),
    ])
    fields = line.split()
    if len(fields) < 3 or fields[1] != "commit":
        raise RuntimeError(
            f"Autoconf gitlink is not registered in QEMU: {SUBMODULE_REL}"
        )
    return fields[2]


def archive_source_signature() -> str:
    candidates = (
        SUBMODULE_DIR / "bootstrap",
        SUBMODULE_DIR / "configure.ac",
        SUBMODULE_DIR / "Makefile.am",
        SUBMODULE_DIR / "bin" / "autoconf.in",
        SUBMODULE_DIR / "bin" / "autom4te.in",
    )
    for path in candidates:
        if not path.is_file():
            raise RuntimeError(
                f"bundled Autoconf source is unavailable: {SUBMODULE_DIR}"
            )
    digest = hashlib.sha256()
    for path in candidates:
        digest.update(str(path.relative_to(SUBMODULE_DIR)).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return "archive-" + digest.hexdigest()


def ensure_source() -> str:
    if not git_checkout_available():
        return archive_source_signature()

    revision = gitlink_revision()
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
            f"Autoconf submodule revision mismatch: {current} != {revision}"
        )
    return revision


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


def copy_source(revision: str, destination: pathlib.Path) -> None:
    shutil.rmtree(destination, ignore_errors=True)
    if git_checkout_available() and (SUBMODULE_DIR / ".git").exists():
        extract_git_archive(SUBMODULE_DIR, revision, destination)
    else:
        shutil.copytree(
            SUBMODULE_DIR,
            destination,
            ignore=shutil.ignore_patterns(".git"),
        )
    (destination / ".tarball-version").write_text(
        staged_version(revision) + "\n", encoding="utf-8"
    )


def suite_usable(prefix: pathlib.Path) -> bool:
    for name in ("autoconf", "autom4te", "autoheader", "autoreconf"):
        path = prefix / "bin" / name
        if not path.is_file() or not os.access(path, os.X_OK):
            return False
        completed = subprocess.run(
            [str(path), "--version"],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if completed.returncode != 0 or "GNU Autoconf" not in completed.stdout:
            return False

    # --version does not load Autom4te's Perl modules or the installed M4
    # libraries.  The bootstrap callers deliberately poison AUTOCONF/AUTOM4TE
    # to prove self-host isolation, so do not let those seed-only sentinels
    # leak into validation of the completed private installation.
    smoke_env = os.environ.copy()
    for key in ("AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF"):
        smoke_env.pop(key, None)

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
) -> str:
    return (
        f"AUTOCONF_BOOTSTRAP_SCHEMA={AUTOCONF_BOOTSTRAP_SCHEMA}\n"
        f"AUTOCONF_GIT_COMMIT={revision}\n"
        f"AUTOMAKE={automake}: {first_line([automake, '--version'])}\n"
        f"ACLOCAL={aclocal}: {first_line([aclocal, '--version'])}\n"
        f"M4={m4}: {gnu_m4_version(m4)}\n"
        f"PERL={perl}: {first_line([perl, '--version'])}\n"
        f"MAKE={make}: {first_line([make, '--version'])}\n"
        f"SEED_SED={seed}\n"
        "PROFILE=tool-only-no-docs\n"
    )


def bootstrap(build_root: pathlib.Path) -> pathlib.Path:
    revision = ensure_source()
    automake, aclocal = select_automake_pair()
    m4 = select_gnu_m4()
    perl = tool("perl", "PERL")
    make = select_gnu_make()
    seed = select_seed_sed()
    tool("realpath")
    tool("mktemp")

    prefix = build_root / "deps" / "autoconf"
    work = build_root / "bootstrap" / "autoconf"
    source = work / "source"
    objects = work / "build"
    marker_path = prefix / ".whp-autoconf-bootstrap"

    marker = marker_text(revision, automake, aclocal, m4, perl, make, seed)
    if (
        marker_path.is_file()
        and marker_path.read_text(encoding="utf-8", errors="replace") == marker
        and suite_usable(prefix)
    ):
        return prefix

    shutil.rmtree(prefix, ignore_errors=True)
    shutil.rmtree(work, ignore_errors=True)
    prefix.parent.mkdir(parents=True, exist_ok=True)
    work.mkdir(parents=True, exist_ok=True)
    copy_source(revision, source)
    objects.mkdir(parents=True, exist_ok=True)

    seed_bin = work / "seed-bin"
    seed_bin.mkdir(parents=True, exist_ok=True)
    seed_link = seed_bin / "sed"
    try:
        seed_link.symlink_to(SED_ADAPTER)
    except OSError:
        shutil.copy2(SED_ADAPTER, seed_link)
        seed_link.chmod(seed_link.stat().st_mode | 0o111)

    # Some Autotools helpers still invoke literal "m4" even when M4 is set.
    # Mirror the validated executable under that canonical name so PATH and the
    # M4 variable always resolve to the same implementation.
    m4_link = seed_bin / "m4"
    try:
        m4_link.symlink_to(m4)
    except OSError:
        shutil.copy2(m4, m4_link)
        m4_link.chmod(m4_link.stat().st_mode | 0o111)

    env = os.environ.copy()
    for key in (
        "BASH_ENV", "ENV", "POSIXLY_CORRECT",
        "AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF",
        "MAKEINFO", "HELP2MAN",
    ):
        env.pop(key, None)
    env["AUTOMAKE"] = automake
    env["ACLOCAL"] = aclocal
    env["M4"] = m4
    env["PERL"] = perl
    env["WHP_SED_SEED"] = seed
    env["SED"] = seed
    env["EMACS"] = "no"
    env["PATH"] = (
        str(seed_bin)
        + os.pathsep
        + str(pathlib.Path(automake).parent)
        + os.pathsep
        + env.get("PATH", "")
    )

    config_shell = explicit_tool("CONFIG_SHELL") or "/bin/sh"
    print(
        f"WHP Autoconf bootstrap: {revision} -> {prefix} "
        f"(Automake {automake}, GNU M4 {m4}, seed sed {seed})",
        file=sys.stderr,
    )

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
        [make, "-j", str(max(1, os.cpu_count() or 1)), *BUILD_TARGETS],
        cwd=objects,
        env=env,
    )
    run_logged(
        [make, *INSTALL_TARGETS, "pkgdata_DATA="],
        cwd=objects,
        env=env,
    )

    if not suite_usable(prefix):
        raise RuntimeError(
            f"bootstrapped Autoconf tool suite is not usable: {prefix}"
        )
    marker_path.write_text(marker, encoding="utf-8")
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
