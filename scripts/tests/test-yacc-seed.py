#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused native Yacc/Bison seed admission and forwarding tests."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds" / "yacc.sh"
POWERPC = ROOT / "scripts" / "bootstrap-powerpc-toolchain-git.bash"


def invoke(arguments, env):
    return subprocess.run(
        ["/bin/sh", str(SEED), *arguments],
        env=env, capture_output=True, text=True, check=False,
    )


def fake_bison(path, banner="bison (GNU Bison) 3.8.2"):
    path.write_text(
        "#!/bin/sh\n"
        "case \"$1\" in\n"
        f"    --version) printf '%s\\n' '{banner}'; exit 0 ;;\n"
        "    --whp-yacc-adapter-probe) exit 2 ;;\n"
        "esac\n"
        "printf 'forwarded:%s\\n' \"$*\"\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


with tempfile.TemporaryDirectory(prefix="whp-yacc-seed-") as temporary:
    root = Path(temporary)
    good = root / "bison-good"
    fake_bison(good)
    env = {**os.environ, "WHP_YACC_SEED": str(good)}
    env.pop("YACC", None)

    result = invoke(["--print-seed"], env)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(good)
    result = invoke(["--check"], env)
    assert result.returncode == 0, result.stderr
    assert "WHP Yacc seed (Bison):" in result.stdout
    result = invoke(["--defines=x.h", "grammar.y"], env)
    assert result.returncode == 0, result.stderr
    assert "forwarded:--defines=x.h grammar.y" in result.stdout

    old = root / "old-bison"
    fake_bison(old, "bison (GNU Bison) 2.3")
    result = invoke(["--print-seed"], {**env, "WHP_YACC_SEED": str(old)})
    assert result.returncode != 0
    assert "WHP_YACC_SEED" in result.stderr

    fake = root / "legacy-yacc"
    fake_bison(fake, "yacc 3.8.2")
    result = invoke(["--print-seed"], {**env, "WHP_YACC_SEED": str(fake)})
    assert result.returncode != 0

    result = invoke(["--print-seed"], {**env, "WHP_YACC_SEED": "bison bad"})
    assert result.returncode != 0

    result = invoke(["--print-seed"], {**env, "WHP_YACC_SEED": str(root / "missing")})
    assert result.returncode != 0

    # Source checkouts may lose executable mode; a self-reference must still
    # be rejected when the adapter is executable on PATH.
    copy = root / "yacc-adapter"
    shutil.copyfile(SEED, copy)
    copy.chmod(0o755)
    result = invoke(["--print-seed"], {**env, "WHP_YACC_SEED": str(copy)})
    assert result.returncode != 0

    # YACC without WHP override remains an explicit, validated selection.
    result = invoke(
        ["--print-seed"],
        {**env, "WHP_YACC_SEED": "", "YACC": str(good)},
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(good)

powerpc_source = POWERPC.read_text(encoding="utf-8")
assert 'seeds/yacc.sh" --print-seed' in powerpc_source
assert 'export YACC BISON' in powerpc_source
print("Yacc seed: native Bison admission and forwarding verified")
