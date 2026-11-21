#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression for legacy AWK field extraction from Git submodule metadata.

The complete LLVM and GRUB bootstraps are deliberately not invoked here.
A tiny offline Git fixture exercises the same direct object lookup syntax.
"""

from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CALLERS = (
    ("scripts/bootstrap-powerpc-clang-core.bash", "LLVM_SUBMODULE_PATH",
     "expected_llvm_revision"),
    ("scripts/bootstrap-i386-efi-grub.bash", "GRUB_SUBMODULE_PATH",
     "expected_revision"),
)
PIN = "0123456789abcdef0123456789abcdef01234567"


def git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True, text=True, capture_output=True,
    )


def main() -> int:
    for filename, variable, target in CALLERS:
        source = (ROOT / filename).read_text(encoding="utf-8")
        lookup = 'git -C "$SOURCE_DIR" rev-parse --verify "HEAD:$' + variable + '"'
        if lookup not in source:
            raise RuntimeError(f"{filename}: expected direct Git lookup is absent")
        if source.index("whp_git_submodule_prepare") > source.index(lookup):
            raise RuntimeError(f"{filename}: gitlink mode must be checked first")
        if "ls-tree HEAD --" in source and "awk '{print $3}'" in source:
            raise RuntimeError(f"{filename}: legacy AWK gitlink parser remains")
        if target not in source:
            raise RuntimeError(f"{filename}: expected pin variable is missing")

    with tempfile.TemporaryDirectory(prefix="whp-awk-gitlink-") as td:
        directory = Path(td)
        git(directory, "init", "-q")
        git(directory, "-c", "user.name=fixture", "-c", "user.email=f@x",
            "commit", "-q", "--allow-empty", "-m", "initial")
        path = "toolchains/llvm project"
        git(directory, "update-index", "--add", "--cacheinfo",
            f"160000,{PIN},{path}")
        git(directory, "-c", "user.name=fixture", "-c", "user.email=f@x",
            "commit", "-q", "-m", "pin")
        result = git(directory, "rev-parse", "--verify", f"HEAD:{path}")
        if result.stdout.strip() != PIN:
            raise RuntimeError("Gitlink object lookup changed its identity")
        missing = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--verify",
             "HEAD:toolchains/not-present"],
            check=False, text=True, capture_output=True,
        )
        if missing.returncode == 0:
            raise RuntimeError("Missing submodule path was accepted")

    print("WHP Gitlink lookups: direct object IDs verified without AWK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
