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
    section = 'submodule "toolchains/make"'
    if section not in parser:
        raise SystemExit("error: GNU Make fork is not registered as toolchains/make")
    if parser[section].get("url") != "https://github.com/retrochristian5000/make.git":
        raise SystemExit("error: toolchains/make does not point at the WHP GNU Make fork")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "toolchains/make", "GNU Make ledger row")
    require(ledger, "GNU Make bootstrap boundary", "GNU Make circularity section")
    require(ledger, "Make -> Make", "GNU Make self-bootstrap warning")
    require(ledger, "build.sh", "GNU Make no-Make bootstrap path")
    require(ledger, "build.cfg", "GNU Make configured-input boundary")

    python_bootstrap = (ROOT / "scripts/bootstrap-python.sh").read_text(encoding="utf-8")
    require(python_bootstrap, "resolve_bootstrap_make()", "Python Make resolver")
    require(python_bootstrap, 'requested_make=${MAKE_CMD:-${MAKE:-}}', "Python MAKE_CMD/MAKE handoff")
    require(python_bootstrap, '"$bootstrap_make" DESTDIR="$install_root" install', "Python selected Make install")

    grub_bootstrap = (ROOT / "scripts/bootstrap-i386-efi-grub.bash").read_text(encoding="utf-8")
    require(grub_bootstrap, 'source "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"', "GRUB shared Make resolver")
    require(grub_bootstrap, 'MAKE_CMD_REQUESTED="${MAKE_CMD:-${MAKE:-}}"', "GRUB MAKE_CMD/MAKE handoff")
    require(grub_bootstrap, 'PATH="$LLVM_TOOL_PATH" "$MAKE_CMD" -C "$build_root"', "GRUB selected Make build")

    prepare_build = (ROOT / "scripts/whp-build/prepare-build.bash").read_text(encoding="utf-8")
    require(
        prepare_build,
        'local requested_make="${MAKE_CMD:-${MAKE:-}}"',
        "late MAKE_CMD/MAKE convergence",
    )

    libisofs = (ROOT / "scripts/ensure-libisofs.py").read_text(encoding="utf-8")
    require(
        libisofs,
        'names = ("gmake", "make") if name == "make" else (name,)',
        "libisofs GNU Make preference",
    )

    libtool = (ROOT / "scripts/ensure-libtool.py").read_text(encoding="utf-8")
    require(libtool, "select_gnu_make()", "Libtool GNU Make resolver")
    require(libtool, 'os.environ.get("MAKE_CMD"', "Libtool MAKE_CMD handoff")
    require(libtool, '"GNU Make" in output', "Libtool GNU Make identity check")

    print("GNU Make dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
