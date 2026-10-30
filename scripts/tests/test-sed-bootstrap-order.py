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

    grep_seed = 'WHP_GREP_SEED=$("$SOURCE_DIR/grep.sh" --print-seed)'
    require(build, grep_seed, "early grep seed selection")
    require(build, "WHP_GREP_LOCKED=1", "validated grep fast path")
    require(build, 'PATH="$WHP_GREP_BIN_DIR:$PATH"', "literal grep PATH binding")
    require(build, "export WHP_GREP_SEED WHP_GREP_LOCKED GREP PATH",
            "same grep implementation for literal and variable calls")
    shim = ROOT / "scripts/whp-build/seed-bin/grep"
    if not shim.is_file():
        raise SystemExit("error: literal grep bridge is missing")

    seed = 'WHP_SED_SEED=$("$SOURCE_DIR/sed.sh" --print-seed)'
    python_bootstrap = '"$SOURCE_DIR/scripts/bootstrap-python.sh"'
    require(build, seed, "early seed sed selection")
    require(build, "export WHP_SED_SEED", "seed sed export")
    require(host_tools, 'if [ -z "${WHP_SED_SEED:-}" ]; then',
            "sed bootstrap retains build.sh seed provenance")
    if "unset WHP_SED_SEED" in host_tools:
        raise SystemExit("error: managed sed bootstrap destroys seed provenance")
    if not build.index(grep_seed) < build.index(seed) < build.index(python_bootstrap):
        raise SystemExit("error: grep, sed, Python bootstrap order has drifted")

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
