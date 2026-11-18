#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise native Automake/aclocal pair selection and seed forwarding."""

from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/automake.sh"


def fake(path: Path, version: str, *, family="GNU automake",
         macro_dir: Path | None = None):
    path.parent.mkdir(parents=True, exist_ok=True)
    macro_path = macro_dir or path.parent / "missing-aclocal-macros"
    libdir = macro_path.parent / ("automake-" + macro_path.name.rsplit("-", 1)[-1])
    system_dir = macro_path.parent / "aclocal"
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) printf "%s\\n" "' + path.name + " (" + family + ") " + version + '";;\n'
        '  --print-ac-dir) printf "%s\\n" ' + shlex.quote(str(system_dir)) + ';;\n'
        '  --print-libdir) printf "%s\\n" ' + shlex.quote(str(libdir)) + ';;\n'
        '  --whp-automake-adapter-probe) exit 2;;\n'
        '  *) printf "called:%s:%s\\n" "' + path.name + '" "$1";;\n'
        'esac\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def run(env: dict[str, str], *args: str):
    return subprocess.run(
        ["/bin/sh", str(SEED), *args], env=env, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
        timeout=10,
    )


def main():
    with tempfile.TemporaryDirectory(prefix="whp-automake-seed-") as temp:
        root = Path(temp)
        selected = root / "selected"
        other = root / "other"
        am = selected / "automake"
        local = selected / "aclocal"
        wrong = other / "aclocal"
        # Unversioned aclocal contains system macros; versioned core macros
        # and Automake's Perl libraries are distinct installation roots.
        macro_dir = root / "prefix with spaces" / "share" / "aclocal-1.16"
        macro_dir.mkdir(parents=True)
        library_dir = macro_dir.parent / "automake-1.16"
        for name in ("Automake/Config.pm", "am/header-vars.am"):
            target = library_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("library content\n")
        for name in ("init.m4", "amversion.m4"):
            (macro_dir / name).write_text("dnl valid macro data\n")
        fake(am, "1.16.5", macro_dir=macro_dir)
        fake(local, "1.16.5", macro_dir=macro_dir)
        fake(wrong, "1.17.0")
        env = {**os.environ, "PATH": str(other) + os.pathsep + str(selected) +
               os.pathsep + "/usr/bin:/bin"}
        for var in ("WHP_AUTOMAKE_SEED", "WHP_ACLOCAL_SEED", "AUTOMAKE", "ACLOCAL"):
            env.pop(var, None)

        result = run(env, "--print-seed")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(am)

        result = run(env, "--print-aclocal")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(local), result.stdout

        result = run(env, "--check-macros")
        assert result.returncode == 0, result.stderr
        assert str(macro_dir) in result.stdout
        assert str(library_dir) in result.stdout

        # A version-correct binary without its versioned macro files is
        # invalid for the Autoconf source bootstrap.
        (macro_dir / "init.m4").unlink()
        missing_macro = run(env, "--check-macros")
        assert missing_macro.returncode != 0
        assert "init.m4" in missing_macro.stderr
        assert run(env, "--print-seed").returncode == 0
        (macro_dir / "init.m4").write_text("dnl restored\n")

        result = run(env, "--aclocal", "--help")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "called:aclocal:--help"

        result = run(env, "--help")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "called:automake:--help"

        # Same-version PATH entries must not silently form a cross-prefix pair.
        local.unlink()
        fake(wrong, "1.16.5")
        result = run(env, "--print-aclocal")
        assert result.returncode != 0
        assert "adjacent" in result.stderr
        explicit_split = dict(env, WHP_AUTOMAKE_SEED=str(am),
                              WHP_ACLOCAL_SEED=str(wrong))
        result = run(explicit_split, "--print-aclocal")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(wrong)
        fake(local, "1.16.5", macro_dir=macro_dir)
        fake(wrong, "1.17.0")

        explicit = dict(env, WHP_ACLOCAL_SEED=str(wrong))
        assert run(explicit, "--check").returncode != 0

        # aclocal alone pins its sibling Automake rather than the first
        # unrelated Automake on PATH (which may be an older release).
        paired = root / "paired-other"
        paired_automake = paired / "automake"
        paired_aclocal = paired / "aclocal"
        fake(paired_automake, "1.17.0")
        fake(paired_aclocal, "1.17.0")
        only_aclocal = dict(env, WHP_ACLOCAL_SEED=str(paired_aclocal))
        result = run(only_aclocal, "--print-seed")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(paired_automake)
        result = run(only_aclocal, "--print-aclocal")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(paired_aclocal)
        result = run(dict(env, ACLOCAL=str(paired_aclocal)), "--print-seed")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(paired_automake)

        bad_banner = selected / "fake-aclocal"
        fake(bad_banner, "1.16.5", family="GNU Autoconf")
        assert run(dict(env, WHP_ACLOCAL_SEED=str(bad_banner)), "--check").returncode != 0

        missing = dict(env, WHP_AUTOMAKE_SEED=str(root / "missing"))
        assert run(missing, "--print-seed").returncode != 0

        recursive = dict(env, WHP_AUTOMAKE_SEED=str(SEED))
        assert run(recursive, "--print-seed").returncode != 0

        # Explicit compiler pair selection has authority over PATH ordering.
        override = dict(env, WHP_AUTOMAKE_SEED=str(am),
                        WHP_ACLOCAL_SEED=str(local))
        assert run(override, "--print-aclocal").stdout.strip() == str(local)

    print("WHP Automake seed and paired aclocal forwarding: verified")


if __name__ == "__main__":
    main()
