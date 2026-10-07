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
    section = 'submodule "toolchains/git"'
    if section not in parser:
        raise SystemExit("error: WHP Git fork is not registered")
    if parser[section].get("url") != "https://github.com/retrochristian5000/git-tools.git":
        raise SystemExit("error: toolchains/git does not point at the WHP Git fork")

    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    require(host_tools, "BOOTSTRAP_GIT=", "Git bootstrap policy")
    require(host_tools, '"$SOURCE_DIR/git.sh" --print-seed', "seed Git boundary")
    require(host_tools, "whp_prepare_foundation_zlib", "pre-Git zlib phase")
    require(host_tools, "git-remote-https", "HTTPS promotion guard")
    require(host_tools, "WHP_GIT_LOCAL", "local Git fallback")

    helper = (ROOT / "scripts/ensure-git.py").read_text(encoding="utf-8")
    require(helper, 'SUBMODULE_REL = pathlib.Path("toolchains/git")', "Git pin")
    require(helper, 'SHA1_REL = pathlib.Path("sha1collisiondetection")', "SHA-1 pin")
    require(helper, '"NO_CURL=YesPlease"', "local transport boundary")
    if '"NO_ICONV=YesPlease"' in helper:
        raise SystemExit(
            "error: managed Git must not combine Darwin PRECOMPOSE_UNICODE with NO_ICONV"
        )
    require(helper, "iconv_prefix", "Darwin iconv dependency")
    require(helper, '"DC_SHA1_SUBMODULE=YesPlease"', "collision-detection source")
    require(helper, 'os.environ.get("WHP_ZLIB_PREFIX", "")', "managed zlib input")
    require(helper, 'variables.append(f"ZLIB_PATH={zlib_dir}")', "Git zlib link path")
    require(helper, "has_https_transport", "managed transport probe")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "Git bootstrap boundary", "Git circularity section")
    require(ledger, "seed Git", "seed Git root")
    require(ledger, "Git -> checkout Git", "self-cycle warning")

    print("WHP Git dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
