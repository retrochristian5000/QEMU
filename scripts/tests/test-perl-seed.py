#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native Perl seed tests without rebuilding Perl or Autotools."""

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "seeds/perl.sh"


def run(env, *args):
    return subprocess.run(
        ["/bin/sh", str(ADAPTER), *args],
        env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=15,
    )


def fake(path: Path, *, output: str = "whp-perl-ok", rc: int = 0):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --whp-perl-adapter-probe) exit 2;;\n'
        '  -e) printf "%s\\n" "' + output + '"; exit ' + str(rc) + ';;\n'
        '  *) printf "forward:%s\\n" "$1";;\n'
        'esac\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def check():
    with tempfile.TemporaryDirectory(prefix="whp-perl-seed-") as directory:
        root = Path(directory)
        good = root / "bin" / "perl"
        bad = root / "bad"
        fake(good)
        fake(bad, output="wrong")
        env = {**os.environ, "PATH": str(root / "bin") + os.pathsep
               + "/usr/bin:/bin"}
        env.pop("PERL", None)
        env.pop("WHP_PERL_SEED", None)

        result = run(env, "--print-seed")
        assert result.returncode == 0, result.stderr
        assert result.stdout.strip() == str(good)
        assert run(env, "--check").returncode == 0
        assert run(env, "--help").stdout.strip() == "forward:--help"

        # The adapter must honor an explicit executable rather than silently
        # falling through to the otherwise usable Perl on PATH.
        invalid = dict(env, WHP_PERL_SEED=str(bad))
        assert run(invalid, "--print-seed").returncode != 0
        missing = dict(env, PERL=str(root / "missing"))
        assert run(missing, "--print-seed").returncode != 0
        recursive = dict(env, WHP_PERL_SEED=str(ADAPTER))
        assert run(recursive, "--print-seed").returncode != 0

        fake(bad, rc=7)
        assert run(dict(env, WHP_PERL_SEED=str(bad)),
                   "--print-seed").returncode != 0
        assert run(dict(env, WHP_PERL_SEED="perl -w"),
                   "--print-seed").returncode != 0

        # Exercise the selected interpreter itself when present. This is not
        # required on machines running the hermetic adapter fixture.
        native = shutil.which("perl")
        if native:
            actual = dict(env, WHP_PERL_SEED=native)
            assert run(actual, "--print-seed").returncode == 0

    print("WHP Perl seed execution and override contracts: verified")


if __name__ == "__main__":
    check()
