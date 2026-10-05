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
    require(ledger, "BOOTSTRAP_MAKE", "GNU Make managed promotion policy")
    require(ledger, "libisofs bootstrap boundary", "libisofs dependency section")
    require(ledger, "zlib", "libisofs zlib root edge")
    require(ledger, "pkg-config/pkgconf", "libisofs pkg-config probe edge")

    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    require(config, "BOOTSTRAP_MAKE", "GNU Make menu configuration")

    shell_menu = (ROOT / "scripts/whp-config/menu-options.def").read_text(encoding="utf-8")
    require(shell_menu, "BOOTSTRAP_MAKE|Host features|Bootstrap/use WHP GNU Make", "GNU Make shell menu option")

    make_bootstrap = (ROOT / "scripts/ensure-make.py").read_text(encoding="utf-8")
    require(make_bootstrap, 'MAKE_BOOTSTRAP_SCHEMA = "4"', "GNU Make bootstrap schema")
    require(make_bootstrap, "GNULIB_COMMIT", "pinned gnulib revision")
    require(make_bootstrap, '"--disable-dependency-tracking"', "Make configure profile")
    require(make_bootstrap, 'companion("autoheader", "AUTOHEADER")', "coherent Autoconf suite")
    require(make_bootstrap, 'versions = {autoconf_version(path) for path in suite}', "Autoconf suite version guard")
    require(make_bootstrap, 'for env_name in ("WHP_BUILD_BASH", "CONFIG_SHELL")', "configuration shell selection")
    require(make_bootstrap, '"CONFIG_SHELL": config_shell', "configuration shell export")
    require(make_bootstrap, '"build_alias", "host_alias", "target_alias"', "configure environment isolation")
    require(make_bootstrap, 'key.startswith(("ac_cv_", "gl_cv_", "make_cv_"))', "Autoconf cache isolation")
    require(make_bootstrap, 'configured_build = objects / "build.sh"', "configured build.sh handoff")
    require(make_bootstrap, 'objects / "config.status"', "configure output validation")
    require(make_bootstrap, 'build_root / "cache" / "gnulib" / GNULIB_COMMIT', "persistent gnulib cache")
    require(make_bootstrap, '"GNULIB_SRCDIR": str(gnulib_source)', "local gnulib handoff")
    require(make_bootstrap, '"--gen", "--no-git"', "offline gnulib regeneration")
    require(make_bootstrap, "build.sh", "GNU Make no-Make compiler stage")
    require(make_bootstrap, "WHP_MAKE_SEED", "GNU Make seed boundary")

    make_resolver = (ROOT / "scripts/whp-build/gnu-make.bash").read_text(encoding="utf-8")
    if "[[" in make_resolver or "local " in make_resolver:
        raise SystemExit("error: early GNU Make resolver is no longer POSIX-sh compatible")

    python_bootstrap = (ROOT / "scripts/bootstrap-python.sh").read_text(encoding="utf-8")
    require(python_bootstrap, "resolve_bootstrap_make()", "Python Make resolver")
    require(python_bootstrap, 'requested_make=${MAKE_CMD:-${MAKE:-}}', "Python MAKE_CMD/MAKE handoff")
    require(python_bootstrap, '"$bootstrap_make" DESTDIR="$install_root" install', "Python selected Make install")

    grub_bootstrap = (ROOT / "scripts/bootstrap-i386-efi-grub.bash").read_text(encoding="utf-8")
    require(grub_bootstrap, 'source "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"', "GRUB shared Make resolver")
    require(grub_bootstrap, 'MAKE_CMD_REQUESTED="${MAKE_CMD:-${MAKE:-}}"', "GRUB MAKE_CMD/MAKE handoff")
    require(grub_bootstrap, 'PATH="$LLVM_TOOL_PATH" "$MAKE_CMD" -C "$build_root"', "GRUB selected Make build")

    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    require(
        build,
        '. "$SOURCE_DIR/scripts/whp-build/gnu-make.bash"',
        "early shared GNU Make resolver",
    )
    require(
        build,
        'WHP_MAKE_REQUESTED=${MAKE_CMD:-${MAKE:-}}',
        "early MAKE_CMD/MAKE convergence",
    )
    require(build, 'export WHP_MAKE_SEED MAKE_CMD MAKE', "early GNU Make seed export")

    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(encoding="utf-8")
    require(host_tools, "BOOTSTRAP_MAKE=", "GNU Make host-tools policy")
    require(host_tools, "scripts/ensure-make.py", "GNU Make managed bootstrap call")
    require(host_tools, "WHP_MAKE_SEED", "GNU Make host-tools seed handoff")
    require(host_tools, "WHP_MAKE_PREFIX/bin/make", "GNU Make promotion executable")

    prepare_build = (ROOT / "scripts/whp-build/prepare-build.bash").read_text(encoding="utf-8")
    require(
        prepare_build,
        'local requested_make="${MAKE_CMD:-${MAKE:-}}"',
        "late MAKE_CMD/MAKE convergence",
    )

    libisofs = (ROOT / "scripts/ensure-libisofs.py").read_text(encoding="utf-8")
    require(libisofs, "def select_gnu_make()", "libisofs GNU Make selector")
    require(
        libisofs,
        'os.environ.get("MAKE_CMD") or os.environ.get("MAKE", "")',
        "libisofs MAKE_CMD/MAKE handoff",
    )
    require(
        libisofs,
        'if version.startswith("GNU Make "):',
        "libisofs GNU Make identity check",
    )

    libtool = (ROOT / "scripts/ensure-libtool.py").read_text(encoding="utf-8")
    require(libtool, "select_gnu_make()", "Libtool GNU Make resolver")
    require(libtool, 'os.environ.get("MAKE_CMD"', "Libtool MAKE_CMD handoff")
    require(libtool, '"GNU Make" in output', "Libtool GNU Make identity check")

    print("GNU Make dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
