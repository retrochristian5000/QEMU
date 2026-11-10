#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Offline contract for the direct GNU autom4te / Autoconf seed pair."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ADAPTER = ROOT / "seeds/autom4te.sh"


def fake(path: Path, version: str, family: str = "GNU Autoconf"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) printf "%s\\n" "' + path.name + " (" + family + ") " + version + '";;\n'
        '  --whp-autom4te-adapter-probe) exit 2;;\n'
        '  *) printf "called:%s:%s\\n" "' + path.name + '" "$1";;\n'
        'esac\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def run(env, *args):
    return subprocess.run(
        ["/bin/sh", str(ADAPTER), *args], env=env,
        text=True, capture_output=True, check=False, timeout=10,
    )


def check():
    with tempfile.TemporaryDirectory(prefix="whp-autom4te-seed-") as tmp:
        root = Path(tmp)
        paired = root / "selected"
        other = root / "other"
        autoconf = paired / "autoconf"
        autom4te = paired / "autom4te"
        unrelated = other / "autoconf"
        fake(autoconf, "2.72")
        fake(autom4te, "2.72")
        fake(unrelated, "2.71")
        env = {**os.environ,
               "PATH": str(paired) + os.pathsep + str(other)
               + os.pathsep + "/usr/bin:/bin"}
        for name in ("AUTOCONF", "AUTOM4TE",
                     "WHP_AUTOCONF_SEED", "WHP_AUTOM4TE_SEED"):
            env.pop(name, None)

        assert run(env, "--print-seed").stdout.strip() == str(autom4te)
        assert run(env, "--print-autoconf").stdout.strip() == str(autoconf)
        assert run(env, "--check").returncode == 0
        assert run(env, "--help").stdout.strip() == "called:autom4te:--help"
        assert run(env, "--autoconf", "--help").stdout.strip() == "called:autoconf:--help"

        # A direct Autoconf override must select its sibling autom4te.
        explicit = dict(env, WHP_AUTOCONF_SEED=str(autoconf))
        assert run(explicit, "--print-seed").stdout.strip() == str(autom4te)
        # Mixed explicit pair is a hard error, not a PATH fallback.
        fake(other / "autom4te", "2.71")
        conflicting = dict(env, WHP_AUTOCONF_SEED=str(autoconf),
                           WHP_AUTOM4TE_SEED=str(other / "autom4te"))
        assert run(conflicting, "--print-seed").returncode != 0
        assert "mismatch" in run(conflicting, "--print-seed").stderr

        # Reject forged GNU identity and recursive adapter selection.
        fake(other / "autom4te", "2.72", family="GNU automake")
        assert run(dict(env, WHP_AUTOM4TE_SEED=str(other / "autom4te")),
                   "--check").returncode != 0
        assert run(dict(env, WHP_AUTOM4TE_SEED=str(ADAPTER)),
                   "--print-seed").returncode != 0
        assert run(dict(env, WHP_AUTOCONF_SEED=str(root / "missing")),
                   "--print-seed").returncode != 0

    print("WHP autom4te seed and Autoconf release pairing: verified")


if __name__ == "__main__":
    check()
