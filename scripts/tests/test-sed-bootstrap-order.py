#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    automake = (ROOT / "scripts/ensure-automake.py").read_text(
        encoding="utf-8"
    )
    autoconf = (ROOT / "scripts/ensure-autoconf.py").read_text(
        encoding="utf-8"
    )
    sed_helper = (ROOT / "scripts/ensure-sed.py").read_text(encoding="utf-8")
    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(
        encoding="utf-8"
    )

    seed = 'WHP_SED_SEED=$("$SOURCE_DIR/sed.sh" --print-seed)'
    python_bootstrap = '"$SOURCE_DIR/scripts/bootstrap-python.sh"'
    require(build, seed, "early seed sed selection")
    require(build, "export WHP_SED_SEED", "seed sed export")
    if build.index(seed) > build.index(python_bootstrap):
        raise SystemExit("error: seed sed is selected after the Python fallback")

    automake_pos = host_tools.index("BOOTSTRAP_AUTOMAKE=")
    autoconf_pos = host_tools.index("BOOTSTRAP_AUTOCONF=")
    sed_pos = host_tools.index("BOOTSTRAP_SED=")
    git_pos = host_tools.index("BOOTSTRAP_GIT=")
    bash_pos = host_tools.index("BOOTSTRAP_BASH=")
    if not automake_pos < autoconf_pos < sed_pos < git_pos < bash_pos:
        raise SystemExit(
            "error: expected host-tool order is "
            "Automake -> Autoconf -> GNU sed -> Git -> Bash"
        )

    require(
        automake,
        'os.environ.get("WHP_SED_SEED", "")',
        "Automake shared seed-sed handoff",
    )
    require(
        sed_helper,
        'env["WHP_SED_SEED"] = seed',
        "GNU sed self-bootstrap seed handoff",
    )
    for helper, name in ((automake, "Automake"), (autoconf, "Autoconf"), (sed_helper, "GNU sed")):
        require(helper, 'env["SED"] = str(SED_ADAPTER)', f"{name} sed adapter handoff")
    require(ledger, "``toolchains/automake``", "Automake registry row")
    require(ledger, "``toolchains/sed``", "GNU sed registry row")
    require(ledger, "sed/Automake bootstrap boundary", "sed ordering ledger")
    require(ledger, "gettext/autopoint", "sed gettext prerequisite")
    require(ledger, "makeinfo", "sed makeinfo prerequisite")

    print("GNU sed bootstrap ordering: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
