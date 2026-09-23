#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITMODULES = ROOT / ".gitmodules"
LEDGER = ROOT / "docs" / "devel" / "whp-dependency-ledger.rst"


def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(GITMODULES, encoding="utf-8")
    paths = [
        parser[section]["path"].strip()
        for section in parser.sections()
        if section.startswith("submodule ") and "path" in parser[section]
    ]

    ledger = LEDGER.read_text(encoding="utf-8")
    missing = [path for path in paths if f"``{path}``" not in ledger]
    if missing:
        raise SystemExit(
            "error: WHP dependency ledger is missing submodules: "
            + ", ".join(sorted(missing))
        )

    required_contracts = {
        "Aften/JACK conditional edge": (
            "Full macOS server builds have a conditional Aften edge",
            "``--client-only`` profile deliberately skips Aften",
        ),
        "AArch64/arm64e distinction": (
            "``aarch64``",
            "``arm64e``",
            "NEON",
            "optimization opportunity",
        ),
        "circularity policy": (
            "Circularity guards",
            "must not make\n   itself its own root dependency",
        ),
        "gitlink authority": (
            "The gitlink recorded by the QEMU commit is authoritative",
        ),
    }
    for label, needles in required_contracts.items():
        for needle in needles:
            if needle not in ledger:
                raise SystemExit(
                    f"error: WHP dependency ledger lost {label}: {needle}"
                )

    if len(paths) != len(set(paths)):
        raise SystemExit("error: duplicate submodule paths in .gitmodules")

    print(f"WHP dependency ledger: {len(paths)} top-level submodules covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
