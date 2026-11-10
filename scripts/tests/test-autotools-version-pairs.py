#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise POSIX bootstrap checks for coherent GNU Autotools releases."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "scripts/whp-build/host-tools.sh"


def tool(path: Path, family: str, version: str, *, exit_code: int = 0):
    path.write_text(
        "#!/bin/sh\n"
        'test "$1" = --version || exit 2\n'
        f"printf '%s\\n' '{path.name} ({family}) {version}'\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    path.chmod(0o755)


def check():
    text = SOURCE.read_text(encoding="utf-8")
    begin = text.index("whp_gnu_tool_version()\n")
    end = text.index("\nWHP_AUTOMAKE_EXPLICIT=0", begin)
    auto_start = text.index("whp_autoconf_pair_usable()\n")
    auto_end = text.index("\nWHP_AUTOCONF_EXPLICIT=0", auto_start)
    functions = text[begin:end] + "\n" + text[auto_start:auto_end]
    with tempfile.TemporaryDirectory(prefix="whp-autotools-version-") as directory:
        root = Path(directory)
        first = root / "automake"
        second = root / "aclocal"
        ac = root / "autoconf"
        am4 = root / "autom4te"
        def probe(function: str, left: Path, right: Path) -> bool:
            script = functions + '\n' + function + ' "$1" "$2"\n'
            result = subprocess.run(
                ["/bin/sh", "-c", script, "sh", str(left), str(right)],
                text=True, capture_output=True, check=False,
            )
            return result.returncode == 0

        tool(first, "GNU automake", "1.16.5")
        tool(second, "GNU automake", "1.16.5")
        assert probe("whp_automake_pair_usable", first, second)
        tool(second, "GNU automake", "1.17.0")
        assert not probe("whp_automake_pair_usable", first, second)
        tool(second, "GNU Autoconf", "1.16.5")
        assert not probe("whp_automake_pair_usable", first, second)
        tool(second, "GNU automake", "not-a-version")
        assert not probe("whp_automake_pair_usable", first, second)
        tool(second, "GNU automake", "1.16.5", exit_code=1)
        assert not probe("whp_automake_pair_usable", first, second)
        tool(ac, "GNU Autoconf", "2.72")
        tool(am4, "GNU Autoconf", "2.72")
        assert probe("whp_autoconf_pair_usable", ac, am4)
        tool(am4, "GNU Autoconf", "2.71")
        assert not probe("whp_autoconf_pair_usable", ac, am4)
        tool(am4, "GNU automake", "2.72")
        assert not probe("whp_autoconf_pair_usable", ac, am4)
        tool(am4, "GNU Autoconf", "2.72")
        am4.chmod(0o644)
        assert not probe("whp_autoconf_pair_usable", ac, am4)
    print("Autotools host version-pair checks: verified")


if __name__ == "__main__":
    check()
