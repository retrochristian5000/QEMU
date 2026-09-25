#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import ast

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    menu = (ROOT / "scripts/whp-config/menu-options.def").read_text(
        encoding="utf-8"
    )
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    helper_path = ROOT / "scripts/ensure-libtool.py"
    helper = helper_path.read_text(encoding="utf-8")
    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(
        encoding="utf-8"
    )

    ast.parse(helper, filename=str(helper_path))

    require(
        gitmodules,
        '[submodule "toolchains/libtool"]',
        "Libtool submodule",
    )
    require(gitmodules, "path = toolchains/libtool", "Libtool submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/libtool.git",
        "WHP Libtool fork URL",
    )
    require(gitmodules, "branch = master", "Libtool fork branch")

    option = (
        "Option('BOOTSTRAP_LIBTOOL', 'Host features', "
        "'Bootstrap/use WHP Libtool'"
    )
    require(config, option, "Libtool bootstrap menu policy")
    require(config, "'BOOTSTRAP_LIBTOOL',", "Libtool tri-state export")
    require(
        menu,
        "BOOTSTRAP_LIBTOOL|Host features|Bootstrap/use WHP Libtool|"
        "choice|auto|auto,y,n|",
        "Libtool menu definition",
    )

    require(build, "BOOTSTRAP_LIBTOOL=", "Libtool default policy")
    require(build, "scripts/ensure-libtool.py", "Libtool bootstrap hook")
    require(build, 'LIBTOOL="$WHP_LIBTOOL_PREFIX/bin/libtool"', "Libtool export")
    require(
        build,
        'LIBTOOLIZE="$WHP_LIBTOOL_PREFIX/bin/libtoolize"',
        "libtoolize export",
    )
    require(build, "ACLOCAL_PATH=", "Libtool aclocal macro path")

    require(helper, "toolchains/libtool", "pinned Libtool source")
    require(helper, "NESTED_SUBMODULES", "nested Libtool source policy")
    require(helper, "gnulib", "pinned gnulib dependency")
    require(helper, "gl-mod/bootstrap", "pinned bootstrap dependency")
    require(helper, '"--no-git"', "offline pinned gnulib bootstrap")
    require(helper, '"--skip-po"', "translation download suppression")
    require(helper, 'env.pop(key, None)', "environment isolation")
    require(helper, '"LIBTOOL", "LIBTOOLIZE"', "self-host cycle guard")
    require(helper, 'LIBTOOL_BOOTSTRAP_SCHEMA = "3"', "cache schema")
    require(helper, "def select_llvm_tool(", "LLVM host-tool selector")
    require(helper, "def select_cxx_compiler(", "LLVM C++ compiler selector")
    require(helper, "def select_linker(", "LLVM linker selector")
    require(helper, '"llvm-ar"', "LLVM archiver preference")
    require(helper, '"llvm-ranlib"', "LLVM ranlib preference")
    require(helper, '"llvm-nm"', "LLVM nm preference")
    require(helper, '"llvm-objdump"', "LLVM objdump preference")
    require(helper, '"llvm-strip"', "LLVM strip preference")
    require(
        helper,
        'arch == "arm64e"',
        "ARM64e linker exception",
    )
    require(
        helper,
        '"ld64.lld" if platform.system() == "Darwin" else "ld.lld"',
        "LLVM linker preference",
    )
    require(helper, "CONFIG_SHELL=", "configuration shell cache identity")
    require(helper, "--disable-ltdl-install", "minimal Libtool profile")
    require(helper, "system_libtool_pair()", "host GNU Libtool auto path")
    require(helper, "GNU libtool", "GNU tool identity check")
    require(helper, "def select_config_shell(", "configuration shell selector")
    require(
        helper,
        'env["CONFIG_SHELL"] = config_shell',
        "Libtool CONFIG_SHELL routing",
    )
    require(helper, 'env["SHELL"] = config_shell', "Libtool make shell routing")
    require(
        helper,
        'SUBMODULE_DIR / "gnulib" / "build-aux" / "git-version-gen"',
        "pinned gnulib version helper",
    )
    require(
        helper,
        'config_shell, str(source_copy / "bootstrap"),',
        "Libtool bootstrap interpreter",
    )
    require(
        helper,
        'config_shell, str(configure),',
        "Libtool configure interpreter",
    )
    if '["/bin/sh",' in helper:
        raise SystemExit(
            "error: Libtool bootstrap still hard-codes /bin/sh as an interpreter"
        )

    early_shell = build.find('CONFIG_SHELL="$WHP_BUILD_BASH"')
    libtool_hook = build.find("scripts/ensure-libtool.py")
    if early_shell < 0 or libtool_hook < 0 or early_shell > libtool_hook:
        raise SystemExit(
            "error: CONFIG_SHELL is not published before Libtool bootstrap"
        )

    require(ledger, "toolchains/libtool", "Libtool dependency ledger entry")
    require(ledger, "Libtool bootstrap", "Libtool dependency edge")

    print("WHP Libtool bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
