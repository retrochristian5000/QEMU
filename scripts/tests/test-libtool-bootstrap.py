#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import ast
import importlib.util
import os
import stat
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def load_helper_module():
    path = ROOT / "scripts/ensure-libtool.py"
    spec = importlib.util.spec_from_file_location("whp_ensure_libtool", path)
    if spec is None or spec.loader is None:
        raise SystemExit("error: could not load ensure-libtool.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def write_fake_m4(path: Path, *, gnu: bool) -> None:
    if gnu:
        body = """#!/bin/sh
if [ "$1" = --gnu ] && [ "$2" = --version ]; then
    printf '%s\\n' 'm4 (GNU M4) 1.4.21'
    exit 0
fi
exit 2
"""
    else:
        body = """#!/bin/sh
if [ "$1" = --gnu ]; then
    printf '%s\\n' "gm4: unrecognized option '--gnu'" >&2
    exit 1
fi
printf '%s\\n' 'Apple M4 compatibility tool'
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_gnu_m4_selector() -> None:
    helper = load_helper_module()
    with tempfile.TemporaryDirectory(prefix="whp-libtool-m4-") as tmp:
        root = Path(tmp)
        good = root / "good-m4"
        bad = root / "bad-m4"
        write_fake_m4(good, gnu=True)
        write_fake_m4(bad, gnu=False)

        old_m4 = os.environ.get("M4")
        try:
            os.environ["M4"] = str(bad)
            try:
                helper.select_gnu_m4()
            except RuntimeError as exc:
                if "--gnu support" not in str(exc):
                    raise SystemExit(
                        "error: invalid M4 diagnostic did not explain GNU capability failure"
                    )
            else:
                raise SystemExit("error: non-GNU M4 was accepted")

            os.environ["M4"] = str(good)
            if helper.select_gnu_m4() != str(good):
                raise SystemExit("error: explicit GNU M4 was not selected")
        finally:
            if old_m4 is None:
                os.environ.pop("M4", None)
            else:
                os.environ["M4"] = old_m4


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
    libtool_m4_path = ROOT / "toolchains/libtool/m4/libtool.m4"
    libtool_m4 = (
        libtool_m4_path.read_text(encoding="utf-8")
        if libtool_m4_path.is_file() else ""
    )
    libltdl_configure_path = ROOT / "toolchains/libtool/libltdl/configure.ac"
    libltdl_configure = (
        libltdl_configure_path.read_text(encoding="utf-8")
        if libltdl_configure_path.is_file() else ""
    )
    libtool_bootstrap_conf_path = ROOT / "toolchains/libtool/bootstrap.conf"
    libtool_bootstrap_conf = (
        libtool_bootstrap_conf_path.read_text(encoding="utf-8")
        if libtool_bootstrap_conf_path.is_file() else ""
    )
    libtool_early_test_path = ROOT / "toolchains/libtool/tests/early-libtool.at"
    libtool_early_test = (
        libtool_early_test_path.read_text(encoding="utf-8")
        if libtool_early_test_path.is_file() else ""
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
    require(
        build,
        'WHP_LIBTOOL_MARKER="$WHP_LIBTOOL_PREFIX/.whp-libtool-bootstrap"',
        "Libtool tool marker handoff",
    )
    require(build, "whp_libtool_marker_tool()", "Libtool marker tool reader")
    require(
        build,
        'sed -n "s#^$1=\\\\([^|]*\\\\)|.*$#\\\\1#p"',
        "safe Libtool marker separator parsing",
    )
    require(build, "AR=$(whp_libtool_marker_tool AR)", "Libtool AR handoff")
    require(build, "whp_libtool_marker_value()", "Libtool marker value reader")
    require(
        build,
        "ARFLAGS=$(whp_libtool_marker_value ARFLAGS)",
        "Libtool ARFLAGS handoff",
    )
    require(build, "AR_FLAGS=$ARFLAGS", "Libtool legacy AR_FLAGS synchronization")
    require(
        build,
        "RANLIB=$(whp_libtool_marker_tool RANLIB)",
        "Libtool ranlib handoff",
    )
    require(build, "NM=$(whp_libtool_marker_tool NM)", "Libtool nm handoff")
    require(
        build,
        "OBJDUMP=$(whp_libtool_marker_tool OBJDUMP)",
        "Libtool objdump handoff",
    )
    require(
        build,
        "STRIP=$(whp_libtool_marker_tool STRIP)",
        "Libtool strip handoff",
    )
    require(build, "LD=$(whp_libtool_marker_tool LD)", "Libtool linker handoff")
    require(
        build,
        "DSYMUTIL=$(whp_libtool_marker_tool DSYMUTIL)",
        "Libtool dsymutil handoff",
    )

    require(helper, "toolchains/libtool", "pinned Libtool source")
    require(helper, "NESTED_SUBMODULES", "nested Libtool source policy")
    require(helper, "gnulib", "pinned gnulib dependency")
    require(helper, "gl-mod/bootstrap", "pinned bootstrap dependency")
    require(helper, '"--no-git"', "offline pinned gnulib bootstrap")
    require(helper, '"--skip-po"', "translation download suppression")
    require(helper, 'env.pop(key, None)', "environment isolation")
    require(helper, '"LIBTOOL", "LIBTOOLIZE"', "self-host cycle guard")
    require(helper, 'LIBTOOL_BOOTSTRAP_SCHEMA = "9"', "cache schema")
    require(
        helper,
        'SUBMODULE_DIR / "bootstrap.conf"',
        "Libtool bootstrap policy cache signature",
    )
    require(
        helper,
        'SUBMODULE_DIR / "m4" / "libtool.m4"',
        "Libtool macro cache signature",
    )
    require(
        helper,
        'SUBMODULE_DIR / "libltdl" / "configure.ac"',
        "standalone libltdl cache signature",
    )
    require(
        helper,
        '"old_archive_cmds="',
        "generated Libtool archive configuration diagnostics",
    )
    require(helper, "def verify_archive_smoke(", "archive smoke test")
    require(helper, 'smoke_env["ARFLAGS"] = ""', "empty ARFLAGS smoke")
    require(helper, '"libwhp-ar-smoke.la"', "static archive smoke output")
    require(
        helper,
        "return os.path.abspath(path)",
        "LLVM multicall alias preservation",
    )
    if "pathlib.Path(path).resolve()" in helper:
        raise SystemExit(
            "error: Libtool tool selection still resolves LLVM multicall aliases"
        )
    require(helper, "def select_llvm_tool(", "LLVM host-tool selector")
    require(helper, "def select_gnu_m4(", "GNU M4 capability selector")
    require(helper, '"--gnu", "--version"', "GNU M4 capability probe")
    require(helper, '"M4": select_gnu_m4()', "GNU M4 bootstrap selection")
    require(helper, "def select_arflags(", "archive flag selector")
    require(helper, 'return "cr"', "llvm-ar default archive flags")
    require(helper, '"ARFLAGS", "AR_FLAGS"', "archive flag environment isolation")
    require(helper, "def select_linker(", "LLVM linker selector")
    require(helper, '"llvm-ar"', "LLVM archiver preference")
    require(helper, '"llvm-ranlib"', "LLVM ranlib preference")
    require(helper, '"llvm-nm"', "LLVM nm preference")
    require(helper, '"llvm-objdump"', "LLVM objdump preference")
    require(helper, '"llvm-strip"', "LLVM strip preference")
    require(helper, '"llvm-dsymutil"', "LLVM dsymutil preference")
    require(helper, '"llvm-lipo"', "LLVM lipo preference")
    require(helper, '"llvm-otool"', "LLVM otool preference")
    require(
        helper,
        'arch == "arm64e"',
        "ARM64e linker exception",
    )
    if helper.find('requested = explicit_tool("LD")') < helper.find('arch == "arm64e"'):
        raise SystemExit(
            "error: inherited LD bypasses the arm64e Apple-linker exception"
        )
    require(
        helper,
        '"ld64.lld" if platform.system() == "Darwin" else "ld.lld"',
        "LLVM linker preference",
    )
    require(
        helper,
        '"OBJDUMP", "llvm-objdump", ("objdump", "false")',
        "optional objdump fallback",
    )
    if libtool_m4:
        require(libtool_m4, "[llvm-ar ar]", "Libtool macro LLVM ar preference")
        require(
            libtool_m4,
            "whether $AR accepts $AR_FLAGS to create an archive",
            "Libtool archiver flag validation",
        )
        require(
            libtool_m4,
            'ARFLAGS:-"\\@S|@lt_ar_flags"',
            "Libtool empty ARFLAGS fallback",
        )
        require(
            libtool_m4,
            "[llvm-ranlib ranlib]",
            "Libtool macro LLVM ranlib preference",
        )
        require(
            libtool_m4,
            "[llvm-strip strip]",
            "Libtool macro LLVM strip preference",
        )
        require(
            libtool_m4,
            "llvm-nm ${ac_tool_prefix}nm",
            "Libtool macro LLVM nm preference",
        )
        require(
            libtool_m4,
            "[llvm-objdump objdump]",
            "Libtool macro LLVM objdump preference",
        )
        require(
            libtool_m4,
            "[llvm-lipo lipo]",
            "Libtool macro LLVM lipo preference",
        )
        require(
            libtool_m4,
            "[llvm-dsymutil dsymutil]",
            "Libtool macro LLVM dsymutil preference",
        )
        require(
            libtool_m4,
            "[llvm-dlltool dlltool]",
            "Libtool macro LLVM dlltool preference",
        )
    require(helper, "CONFIG_SHELL=", "configuration shell cache identity")
    require(helper, "--disable-ltdl-install", "minimal Libtool profile")
    require(helper, "system_libtool_pair()", "host GNU Libtool auto path")
    require(helper, "GNU libtool", "GNU tool identity check")
    require(
        helper,
        '"generated Libtool shell diverged from bootstrap shell: "',
        "generated Libtool shell identity guard",
    )
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
        '"rev-list", "--count", revision',
        "Libtool archive macro serial reconstruction",
    )
    require(
        helper,
        '(destination / ".serial").write_text(',
        "Libtool archive .serial materialization",
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
    native_llvm_hook = build.find("scripts/bootstrap-native-clang.sh")
    libtool_hook = build.find("scripts/ensure-libtool.py")
    libisofs_hook = build.find("scripts/ensure-libisofs.py")
    llvm_tool_handoff = build.find("AR=$(whp_libtool_marker_tool AR)")
    if early_shell < 0 or libtool_hook < 0 or early_shell > libtool_hook:
        raise SystemExit(
            "error: CONFIG_SHELL is not published before Libtool bootstrap"
        )
    if native_llvm_hook < 0 or libtool_hook < 0 or native_llvm_hook > libtool_hook:
        raise SystemExit(
            "error: Libtool is bootstrapped before the native LLVM toolchain"
        )
    if (
        llvm_tool_handoff < 0
        or libisofs_hook < 0
        or llvm_tool_handoff > libisofs_hook
    ):
        raise SystemExit(
            "error: Libtool LLVM host tools are not exported before libisofs"
        )

    if libtool_bootstrap_conf:
        require(
            libtool_bootstrap_conf,
            "SHELL=$CONFIG_SHELL",
            "bootstrap shell synchronization",
        )
        require(
            libtool_bootstrap_conf,
            "export SHELL",
            "bootstrap shell export",
        )

    if libltdl_configure:
        require(
            libltdl_configure,
            'AR_FLAGS=cr',
            "standalone libltdl archive default",
        )
        require(
            libltdl_configure,
            'test -n "${ARFLAGS-}"',
            "standalone libltdl empty-flag handling",
        )

    if libtool_early_test:
        require(
            libtool_early_test,
            "ARFLAGS= $LIBTOOL --mode=link",
            "empty ARFLAGS archive regression test",
        )

    test_gnu_m4_selector()

    require(ledger, "toolchains/libtool", "Libtool dependency ledger entry")
    require(ledger, "Libtool bootstrap", "Libtool dependency edge")

    print("WHP Libtool bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
