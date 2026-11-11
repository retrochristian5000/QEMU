#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(ROOT / ".gitmodules", encoding="utf-8")
    section = 'submodule "toolchains/wine"'
    if section not in parser:
        raise SystemExit("error: Wine fork is not registered as toolchains/wine")
    if parser[section].get("url") != "https://github.com/retrochristian5000/water.git":
        raise SystemExit("error: toolchains/wine does not point at the WHP Wine fork")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "toolchains/wine", "Wine ledger row")
    require(ledger, "Wine and Windows ABI validation", "Wine policy section")
    for tool in ("winegcc", "winebuild", "widl", "wrc", "winedump"):
        require(ledger, tool, f"Wine tool {tool}")
    require(ledger, "LLVM -> Windows artifact -> Wine validation", "LLVM-to-Wine direction")
    require(ledger, "arm64ec", "Windows ARM64EC distinction")
    require(ledger, "arm64e", "Apple ARM64e distinction")
    require(ledger, "--with-wine-tools=DIR", "Wine cross-build tools boundary")
    require(ledger, "must not\n   become a prerequisite for bootstrapping the LLVM compiler", "LLVM circularity guard")

    print("Wine dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
