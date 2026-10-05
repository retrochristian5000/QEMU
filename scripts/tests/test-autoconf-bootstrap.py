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
    require(helper, 'AUTOCONF_BOOTSTRAP_SCHEMA = "3"', "bootstrap schema")
    require(helper, '[path, "--gnu", "--version"]', "GNU M4 capability probe")
    require(
        helper,
        '"/opt/homebrew/opt/m4/bin/m4"',
        "Apple Silicon Homebrew M4 preference",
    )
    require(
        helper,
        '"/usr/local/opt/m4/bin/m4"',
        "Intel Homebrew M4 preference",
    )
    require(helper, 'for name in ("m4", "gm4")', "canonical M4 fallback order")
    require(helper, 'm4_link = seed_bin / "m4"', "literal M4 bootstrap shim")
    require(helper, '"AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF"', "self-host isolation")
    require(helper, 'str(source / "bootstrap")', "source self-bootstrap")
    require(helper, '"install-binSCRIPTS"', "tool-only executable install")
    require(helper, '"install-dist_perllibDATA"', "Autom4te Perl library install")
    require(helper, '"install-nodist_pkgdataDATA"', "generated package-data install")
    require(helper, '"install-dist_autoconflibDATA"', "Autoconf source library install")
    require(helper, '"install-nodist_autoconflibDATA"', "Autoconf frozen library install")
    require(helper, '"install-nodist_autoscanlibDATA"', "Autoscan generated-data install")
    require(helper, '"install-dist_m4sugarlibDATA"', "M4sugar source library install")
    require(helper, '"install-nodist_m4sugarlibDATA"', "M4sugar frozen library install")
    require(helper, '"install-dist_autotestlibDATA"', "Autotest source library install")
    require(helper, '"install-nodist_autotestlibDATA"', "Autotest frozen library install")
    require(helper, '"install-dist_buildauxDATA"', "Autoconf build-aux install")
    require(helper, 'input="AC_INIT([whp-bootstrap-smoke],[1])', "installed runtime smoke")
    require(helper, '"pkgdata_DATA="', "documentation-free install override")
    for stale_target in (
        '"install-perllibDATA"',
        '"install-autoconflibDATA"',
        '"install-autoscanlibDATA"',
        '"install-m4sugarlibDATA"',
        '"install-autotestlibDATA"',
        '"install-buildauxDATA"',
    ):
        if stale_target in helper:
            raise SystemExit(
                f"error: stale collapsed Automake install target remains: {stale_target}"
            )
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
