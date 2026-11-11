#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the real POSIX Ninja command validator without invoking bootstraps."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HOST_TOOLS = ROOT / "scripts/whp-build/host-tools.sh"


def check() -> None:
    text = HOST_TOOLS.read_text(encoding="utf-8")
    start = text.index("whp_ninja_command_usable()\n")
    end = text.index("\n# QEMU's normal Meson path", start)
    function = text[start:end]
    assert function.count("--version") == 1
    assert "command -v" in function
    assert 'if [ "$BOOTSTRAP_NINJA" = 1 ]; then' in text[end:]
    assert 'whp_ninja_command_usable "$NINJA_CMD"' in text[end:]
    host_probe = text.index('NINJA_CMD=$(command -v ninja', end)
    bundled_fallback = text.index(
        'if [ -z "${NINJA_CMD:-}" ] && [ "$BOOTSTRAP_NINJA" != 0 ]', end
    )
    retry_probe = text.index(
        'if [ -n "${NINJA_CMD:-}" ] &&\n'
        '       ! whp_ninja_command_usable "$NINJA_CMD"; then', host_probe
    )
    assert host_probe < retry_probe < bundled_fallback
    assert text.count('! whp_ninja_command_usable "$NINJA_CMD"') == 3

    with tempfile.TemporaryDirectory(prefix="whp-ninja-call-") as temp:
        directory = Path(temp)
        good = directory / "good-ninja"
        bad = directory / "bad-ninja"
        good.write_text("#!/bin/sh\n[ \"$1\" = --version ] || exit 33\nprintf '1.12.0\\n'\n")
        bad.write_text("#!/bin/sh\nexit 49\n")
        good.chmod(0o755)
        bad.chmod(0o755)
        env = os.environ.copy()
        env["PATH"] = str(directory) + os.pathsep + env.get("PATH", "")
        for candidate, success in (
            (str(good), True),
            ("good-ninja", True),
            (str(bad), False),
            (str(directory / "absent"), False),
            ("bad-ninja", False),
        ):
            script = function + '\nwhp_ninja_command_usable "$1" || exit 1\n'
            result = subprocess.run(
                ["/bin/sh", "-c", script, "sh", candidate],
                env=env, text=True, capture_output=True, check=False,
            )
            assert (result.returncode == 0) == success, (
                candidate, result.returncode, result.stderr
            )
            if success:
                script += 'printf "%s\\n" "$NINJA_CMD"\n'
                result = subprocess.run(
                    ["/bin/sh", "-c", script, "sh", candidate],
                    env=env, text=True, capture_output=True, check=False,
                )
                assert result.returncode == 0, result.stderr
                assert result.stdout.strip() == str(good), result.stdout

    print("Ninja bootstrap call contract: native command validation verified")


if __name__ == "__main__":
    check()
