#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Managed Gawk bootstrap policy and root-seed regression checks."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ensure-gawk.py"
spec = importlib.util.spec_from_file_location("whp_ensure_gawk", SCRIPT)
assert spec and spec.loader
gawk = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gawk)


def check():
    modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert '[submodule "toolchains/gawk"]' in modules
    assert "https://github.com/retrochristian5000/gawk.git" in modules
    tree = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", "toolchains/gawk"],
        text=True, capture_output=True, check=False,
    )
    assert tree.returncode == 0 and tree.stdout.startswith("160000 commit "), (
        "managed Gawk must have a pinned Git submodule commit"
    )
    src = SCRIPT.read_text(encoding="utf-8")
    assert 'reconcile_submodule(ROOT, REL)' in src
    assert 'stage_source(revision, source)' in src
    assert 'validate_managed_gawk(built)' in src
    assert 'validate_managed_gawk(executable)' in src
    assert '"SOURCE_REVISION="' in src

    host = (ROOT / "scripts/whp-build/host-tools.sh").read_text()
    assert host.index("BOOTSTRAP_AUTOCONF=") < host.index("BOOTSTRAP_GAWK=")
    assert host.index("BOOTSTRAP_GAWK=") < host.index("BOOTSTRAP_MAKE=")
    assert 'WHP_AWK_SEED=$WHP_GAWK_CMD' in host
    assert 'WHP_AWK_LOCKED=1' in host
    assert "BOOTSTRAP_GAWK=1 requires" in host
    config = (ROOT / "scripts/whp-config/config.py").read_text()
    assert "Option('BOOTSTRAP_GAWK', 'Host features'" in config
    assert "'BOOTSTRAP_GAWK'," in config
    build = (ROOT / "build.sh").read_text()
    assert 'WHP_AWK_BOOTSTRAP_SEED=$WHP_AWK_SEED' in build
    assert 'export WHP_AWK_BOOTSTRAP_SEED WHP_AWK_SEED' in build

    # Semantic rather than banner-only testing: any non-AWK executable fails.
    with tempfile.TemporaryDirectory(prefix="whp-gawk-policy-") as directory:
        fake = Path(directory) / "gawk"
        fake.write_text("#!/bin/sh\nprintf '%s\\n' 'GNU Awk 99.99'\n")
        fake.chmod(0o755)
        assert not gawk.validate_awk(fake)
        assert not gawk.validate_managed_gawk(fake)
        native = shutil.which("awk")
        if native:
            assert gawk.validate_awk(Path(native))
            # POSIX-compatible but non-GNU AWK is acceptable as a root seed,
            # not as a substitute for the pinned managed Gawk build.
            version = subprocess.run(
                [native, "--version"], capture_output=True, text=True,
                check=False,
            )
            if version.returncode or not version.stdout.startswith("GNU Awk "):
                assert not gawk.validate_managed_gawk(Path(native))

    # Prove the builder recovers the *root* seed after $AWK has been promoted.
    original = shutil.which("awk")
    if original:
        env = {
            "WHP_AWK_BOOTSTRAP_SEED": original,
            "WHP_AWK_SEED": "/not-yet-built/deps/gawk/bin/gawk",
            "AWK": "/not-yet-built/deps/gawk/bin/gawk",
        }
        with mock.patch.dict(os.environ, env, clear=False):
            assert gawk.seed_awk() == original

    # These checks are source-graph tests; they do not claim to compile Gawk.
    print("Pinned Gawk root seed and promotion contracts: verified")


if __name__ == "__main__":
    check()
