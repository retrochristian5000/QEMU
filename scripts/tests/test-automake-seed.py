#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise native Automake/aclocal pair selection and seed forwarding."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/automake.sh"


def fake(path: Path, version: str, *, family="GNU automake"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) printf "%s\\n" "' + path.name + " (" + family + ") " + version + '";;\n'
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
        fake(am, "1.16.5")
        fake(local, "1.16.5")
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

        result = run(env, "--aclocal", "--help")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "called:aclocal:--help"

        result = run(env, "--help")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == "called:automake:--help"

        explicit = dict(env, WHP_ACLOCAL_SEED=str(wrong))
        assert run(explicit, "--check").returncode != 0

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
