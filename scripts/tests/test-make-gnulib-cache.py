#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import shutil
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "ensure-make.py"


def run(*args: str, cwd: pathlib.Path | None = None) -> str:
    completed = subprocess.run(
        args,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(
            "error: command failed: "
            + " ".join(args)
            + ("\n" + completed.stderr if completed.stderr else "")
        )
    return completed.stdout.strip()


def main() -> int:
    git = shutil.which("git")
    if not git:
        raise SystemExit("error: git is required for GNU Make gnulib cache test")

    spec = importlib.util.spec_from_file_location("whp_ensure_make", HELPER)
    if spec is None or spec.loader is None:
        raise SystemExit("error: could not load scripts/ensure-make.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        origin = root / "origin"
        build_root = root / "build"

        run(git, "init", str(origin))
        gnulib_tool = origin / "gnulib-tool"
        gnulib_tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        gnulib_tool.chmod(0o755)
        run(git, "-C", str(origin), "add", "gnulib-tool")
        run(
            git, "-C", str(origin),
            "-c", "user.name=WHP test",
            "-c", "user.email=whp-test@example.invalid",
            "commit", "-m", "test gnulib seed",
        )
        revision = run(git, "-C", str(origin), "rev-parse", "HEAD")

        module.GNULIB_URL = str(origin)
        module.GNULIB_COMMIT = revision

        first = module.ensure_gnulib_cache(build_root, git)
        expected = build_root / "cache" / "gnulib" / revision
        if first != expected:
            raise SystemExit(
                f"error: gnulib cache path drifted: {first} != {expected}"
            )
        if not module.gnulib_cache_usable(first, git):
            raise SystemExit("error: freshly populated gnulib cache is unusable")

        # Remove the only source repository. Cache reuse must now be fully
        # local; any attempted fetch will fail this second call.
        shutil.rmtree(origin)
        second = module.ensure_gnulib_cache(build_root, git)
        if second != first:
            raise SystemExit("error: gnulib cache path changed on reuse")
        if not module.gnulib_cache_usable(second, git):
            raise SystemExit("error: reused gnulib cache became unusable")

    print("GNU Make gnulib cache reuse: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
