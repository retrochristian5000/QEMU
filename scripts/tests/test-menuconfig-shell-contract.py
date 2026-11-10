#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""POSIX menuconfig argument and schema-field parsing regressions."""

from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "scripts/whp-config/config.py"
SHELL_MENU = ROOT / "scripts/whp-config/menuconfig.sh"
SCHEMA = ROOT / "scripts/whp-config/menu-options.def"


def run(shell: Path, config: Path, cwd: Path, *args: str, input_text: str = ""):
    return subprocess.run(
        ["/bin/sh", str(shell), str(config), *args],
        cwd=cwd, input=input_text, text=True,
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=False, timeout=15,
    )


def check():
    subprocess.run(["/bin/sh", "-n", str(SHELL_MENU)], check=True)
    with tempfile.TemporaryDirectory(prefix="whp-menu-shell-") as tmp:
        root = Path(tmp)
        shell = root / "menuconfig.sh"
        schema = root / "menu-options.def"
        original = SCHEMA.read_text(encoding="utf-8")
        shell.write_text(SHELL_MENU.read_text(encoding="utf-8"),
                         encoding="utf-8")
        # A label containing a glob is valid data. Its matching filenames
        # must never turn the label into extra shell positional parameters.
        lines = original.splitlines()
        assert lines[1].startswith("BUILD_QEMU_IMG|")
        fields = lines[1].split("|")
        fields[2] = "qemu-img *"
        lines[1] = "|".join(fields)
        schema.write_text("\n".join(lines) + "\n", encoding="utf-8")
        (root / "qemu-img first").write_text("")
        (root / "qemu-img second").write_text("")
        config = root / ".whpconfig"

        result = run(shell, config, root, input_text="1\ns\nq\n")
        assert result.returncode == 0, result.stderr
        saved = config.read_text(encoding="utf-8")
        assert "BUILD_QEMU_IMG=n\n" in saved, saved
        assert "Changed qemu-img *: y -> n" in result.stdout, result.stdout

        # A second positional argument must not be silently discarded.
        invalid = run(shell, config, root, "--dump", "--unrecognized")
        assert invalid.returncode == 2, invalid
        assert "only --dump" in invalid.stderr, invalid.stderr
        assert not config.with_name(config.name + ".tmp").exists()

        dump = run(shell, config, root, "--dump")
        assert dump.returncode == 0, dump.stderr
        assert "BOOTSTRAP_GAWK" in dump.stdout, dump.stdout

    # The full semantic schema is checked by test-python-menu-fallback.py.
    # This fixture deliberately modifies only an *ephemeral* copy.
    print("WHP POSIX menu schema parsing and argument contract: verified")


if __name__ == "__main__":
    check()
