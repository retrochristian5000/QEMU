#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate WHP-owned POSIX sh versus GNU Bash interpreter boundaries.

This is an L1 syntax/contract check, not a claim of full cross-host runtime
portability. Upstream QEMU scripts not owned by the WHP shell inventory are
deliberately outside this test.
"""

from __future__ import annotations

import pathlib
import re
import shutil
import subprocess

ROOT = pathlib.Path(__file__).resolve().parents[2]
INVENTORY = ROOT / "scripts/whp-build/shell-inventory.bash"


def inventory_paths(text: str, variable: str) -> list[pathlib.Path]:
    match = re.search(rf"^{variable}=\\(\\n(.*?)^\\)", text, re.M | re.S)
    if not match:
        raise RuntimeError(f"missing inventory: {variable}")
    paths = re.findall(r'"\\$SOURCE_DIR/([^"\\n]+)"', match.group(1))
    if not paths:
        raise RuntimeError(f"empty inventory: {variable}")
    return [ROOT / path for path in paths]


def syntax_check(interpreter: str, path: pathlib.Path) -> None:
    result = subprocess.run(
        [interpreter, "-n", str(path)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode:
        raise RuntimeError(
            f"{path.relative_to(ROOT)} is not valid {interpreter} syntax: "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def main() -> int:
    sh = shutil.which("sh")
    bash = shutil.which("bash")
    if not sh or not bash:
        raise RuntimeError("shell-dialect test requires host sh and GNU Bash")

    inventory = INVENTORY.read_text(encoding="utf-8")
    posix = inventory_paths(inventory, "WHP_POSIX_BUILD_SCRIPTS")
    bash_files = inventory_paths(inventory, "WHP_BASH_BUILD_SCRIPTS")

    # Every seed is a POSIX launcher even if a newly added seed has not yet
    # been added to the hand-maintained build entrypoint inventory.
    seeds = sorted((ROOT / "seeds").glob("*.sh"))
    modules = sorted((ROOT / "scripts/whp-build").glob("*.sh"))
    posix = sorted(set(posix + seeds + modules))

    for path in posix:
        if not path.is_file() or path.suffix != ".sh":
            raise RuntimeError(f"missing/non-sh POSIX shell script: {path}")
        first = path.read_text(encoding="utf-8").splitlines()[0]
        # A sourced module may have comments instead of a shebang. Scripts
        # that declare an interpreter must declare POSIX sh, never Bash.
        if first.startswith("#!") and first != "#!/bin/sh":
            raise RuntimeError(
                f"{path.relative_to(ROOT)} declares a non-POSIX interpreter: {first}"
            )
        syntax_check(sh, path)

    for path in bash_files:
        if not path.is_file() or path.suffix != ".bash":
            raise RuntimeError(f"missing/non-bash Bash implementation: {path}")
        first = path.read_text(encoding="utf-8").splitlines()[0]
        if first.startswith("#!") and not (
            first == "#!/bin/bash" or first == "#!/usr/bin/env bash"
        ):
            raise RuntimeError(
                f"{path.relative_to(ROOT)} declares a non-Bash interpreter: {first}"
            )
        syntax_check(bash, path)

    print(
        f"WHP shell dialects: {len(posix)} POSIX .sh and "
        f"{len(bash_files)} Bash .bash syntax/entry contracts verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
