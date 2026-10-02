#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-autoconf.py").read_text(encoding="utf-8")
    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/autoconf"]', "Autoconf submodule")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/autoconf.git",
        "WHP Autoconf fork URL",
    )
    require(helper, 'SUBMODULE_REL = pathlib.Path("toolchains/autoconf")', "pinned source")
    require(helper, 'AUTOCONF_BOOTSTRAP_SCHEMA = "1"', "bootstrap schema")
    require(helper, '"AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF"', "self-host isolation")
    require(helper, 'str(source / "bootstrap")', "source self-bootstrap")
    require(helper, '"install-binSCRIPTS"', "tool-only executable install")
    require(helper, '"install-autoconflibDATA"', "Autoconf library install")
    require(helper, '"install-m4sugarlibDATA"', "M4sugar library install")
    require(helper, '"pkgdata_DATA="', "documentation-free install override")
    require(
        config,
        "Option('BOOTSTRAP_AUTOCONF', 'Host features', 'Bootstrap/use WHP Autoconf'",
        "Autoconf menu option",
    )
    require(config, "'BOOTSTRAP_AUTOCONF',", "Autoconf shell export")

    order = [
        host_tools.index("BOOTSTRAP_AUTOMAKE="),
        host_tools.index("BOOTSTRAP_AUTOCONF="),
        host_tools.index("BOOTSTRAP_SED="),
    ]
    if order != sorted(order) or len(set(order)) != len(order):
        raise SystemExit(
            "error: managed Autoconf is not ordered Automake -> Autoconf -> sed"
        )

    require(ledger, "``toolchains/autoconf``", "Autoconf registry row")
    require(ledger, "Autoconf bootstrap boundary", "Autoconf boundary")
    require(ledger, "seed Autoconf/autom4te", "Autoconf cycle guard")

    print("WHP Autoconf bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
