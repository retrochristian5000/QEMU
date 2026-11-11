#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression for the seed that breaks the Automake/Autoconf source cycle."""

import importlib.util
import os
from pathlib import Path
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "whp_automake_cycle", ROOT / "scripts/ensure-automake.py")
assert spec and spec.loader
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


def fake_tool(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "#!/bin/sh\n"
        'case "$1" in\n'
        '  --version) printf "%s\\n" "' + path.name
        + ' (GNU Autoconf) 2.72";;\n'
        '  --whp-autom4te-adapter-probe) exit 2;;\n'
        '  *) exit 0;;\n'
        'esac\n',
        encoding="utf-8",
    )
    path.chmod(0o755)


def main():
    with tempfile.TemporaryDirectory(prefix="whp-autotools-cycle-") as temp:
        base = Path(temp)
        external = base / "seed"
        build = base / "build"
        a = external / "autoconf"
        b = external / "autom4te"
        fake_tool(a)
        fake_tool(b)
        env = {"AUTOCONF": str(a), "AUTOM4TE": str(b)}
        with mock.patch.dict(os.environ, env, clear=False):
            assert module.select_seed_autoconf_pair(build) == (str(a), str(b))

        inside = build / "deps" / "autoconf" / "bin"
        fake_tool(inside / "autoconf")
        fake_tool(inside / "autom4te")
        for key in ("AUTOCONF", "AUTOM4TE"):
            env = {"AUTOCONF": str(a), "AUTOM4TE": str(b)}
            env[key] = str(inside / key.lower())
            try:
                with mock.patch.dict(os.environ, env, clear=False):
                    module.select_seed_autoconf_pair(build)
            except RuntimeError as exc:
                assert "independent seed" in str(exc)
            else:
                raise AssertionError(f"managed {key} was accepted as seed")
        with mock.patch.dict(os.environ, {
            "AUTOCONF": str(base / "missing-autoconf"),
            "AUTOM4TE": str(b),
        }, clear=False):
            try:
                module.select_seed_autoconf_pair(build)
            except RuntimeError as exc:
                assert "source-bootstrap cycle" in str(exc)
            else:
                raise AssertionError("missing seed Autoconf was accepted")
    print("Automake/Autoconf seed cycle guard: verified")


if __name__ == "__main__":
    main()
