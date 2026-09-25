#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import tempfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")



def load_helper_module():
    path = ROOT / "scripts/ensure-libisofs.py"
    spec = importlib.util.spec_from_file_location("whp_ensure_libisofs", path)
    if spec is None or spec.loader is None:
        raise SystemExit("error: could not load ensure-libisofs.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_incremental_workspace() -> None:
    helper = load_helper_module()
    if not hasattr(helper, "incremental_build_enabled"):
        raise SystemExit("error: libisofs bootstrap has no incremental policy parser")
    if not hasattr(helper, "prepare_workspace"):
        raise SystemExit("error: libisofs bootstrap has no reusable workspace planner")

    with mock.patch.dict(os.environ, {}, clear=False):
        os.environ.pop("WHP_INCREMENTAL_BUILD", None)
        if not helper.incremental_build_enabled():
            raise SystemExit("error: libisofs incremental builds must default on")
        for value in ("1", "y", "yes", "true", "on"):
            os.environ["WHP_INCREMENTAL_BUILD"] = value
            if not helper.incremental_build_enabled():
                raise SystemExit(f"error: incremental value {value!r} was rejected")
        for value in ("0", "n", "no", "false", "off"):
            os.environ["WHP_INCREMENTAL_BUILD"] = value
            if helper.incremental_build_enabled():
                raise SystemExit(f"error: clean-build value {value!r} was ignored")
        os.environ["WHP_INCREMENTAL_BUILD"] = "broken"
        try:
            helper.incremental_build_enabled()
        except RuntimeError:
            pass
        else:
            raise SystemExit("error: invalid WHP_INCREMENTAL_BUILD was accepted")

    with tempfile.TemporaryDirectory(prefix="whp-libisofs-incremental-") as tmp:
        root = Path(tmp)
        work = root / "bootstrap/libisofs"
        source = work / "source"
        objects = work / "build"
        prefix = root / "deps/libisofs"
        source.mkdir(parents=True)
        objects.mkdir(parents=True)
        prefix.mkdir(parents=True)
        (source / "old-source.c").write_text("old", encoding="utf-8")
        (objects / "keep.o").write_text("object", encoding="utf-8")
        (prefix / "keep.pc").write_text("installed", encoding="utf-8")
        (work / ".whp-libisofs-workspace").write_text(
            "identity\n", encoding="utf-8"
        )

        reused = helper.prepare_workspace(
            work, prefix, source, "identity\n", incremental=True
        )
        if not reused:
            raise SystemExit("error: compatible libisofs workspace was not reused")
        if not (objects / "keep.o").is_file():
            raise SystemExit("error: incremental libisofs rebuild deleted objects")
        if not (prefix / "keep.pc").is_file():
            raise SystemExit("error: incremental libisofs rebuild deleted prefix")
        if source.exists():
            raise SystemExit("error: incremental libisofs rebuild kept stale source copy")

        source.mkdir(parents=True)
        (source / "new-source.c").write_text("new", encoding="utf-8")
        reused = helper.prepare_workspace(
            work, prefix, source, "different\n", incremental=True
        )
        if reused:
            raise SystemExit("error: incompatible libisofs workspace was reused")
        if (objects / "keep.o").exists() or (prefix / "keep.pc").exists():
            raise SystemExit("error: incompatible libisofs objects were preserved")

        objects.mkdir(parents=True, exist_ok=True)
        prefix.mkdir(parents=True, exist_ok=True)
        source.mkdir(parents=True, exist_ok=True)
        (objects / "clean.o").write_text("object", encoding="utf-8")
        (prefix / "clean.pc").write_text("installed", encoding="utf-8")
        (work / ".whp-libisofs-workspace").write_text(
            "different\n", encoding="utf-8"
        )
        reused = helper.prepare_workspace(
            work, prefix, source, "different\n", incremental=False
        )
        if reused:
            raise SystemExit("error: WHP_INCREMENTAL_BUILD=0 reused libisofs state")
        if (objects / "clean.o").exists() or (prefix / "clean.pc").exists():
            raise SystemExit("error: clean libisofs rebuild preserved old state")

def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-libisofs.py").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    workflow = (
        ROOT / ".github/workflows/native-llvm-macos.yml"
    ).read_text(encoding="utf-8")
    libisofs_root = ROOT / "toolchains/libisofs"
    libisofs_util = (
        (libisofs_root / "libisofs/util.c").read_text(encoding="utf-8")
        if (libisofs_root / "libisofs/util.c").is_file() else ""
    )
    libisofs_data_source = (
        (libisofs_root / "libisofs/data_source.c").read_text(encoding="utf-8")
        if (libisofs_root / "libisofs/data_source.c").is_file() else ""
    )
    libisofs_fs_local = (
        (libisofs_root / "libisofs/fs_local.c").read_text(encoding="utf-8")
        if (libisofs_root / "libisofs/fs_local.c").is_file() else ""
    )

    require(
        gitmodules,
        '[submodule "toolchains/libisofs"]',
        "libisofs submodule declaration",
    )
    require(gitmodules, "path = toolchains/libisofs", "libisofs submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/libisofs.git",
        "WHP libisofs fork URL",
    )
    require(gitmodules, "branch = master", "libisofs fork branch")

    require(
        config,
        "Option('BOOTSTRAP_LIBISOFS', 'Host features', "
        "'Bootstrap/use WHP libisofs', 'choice', 'auto', "
        "('auto', 'y', 'n'))",
        "menuconfig libisofs bootstrap policy",
    )
    require(config, "'BOOTSTRAP_LIBISOFS',", "libisofs tri-state export")

    require(
        build,
        "BOOTSTRAP_LIBISOFS=${BOOTSTRAP_LIBISOFS:-auto}",
        "libisofs bootstrap default",
    )
    require(build, "scripts/ensure-libisofs.py", "libisofs bootstrap hook")
    require(build, "LIBISOFS_BOOTSTRAP_MODE=force", "forced fork policy")
    require(build, "WHP_LIBISOFS_PREFIX", "private libisofs prefix")
    require(build, "PKG_CONFIG_PATH=", "libisofs pkg-config handoff")

    require(helper, 'toolchains/libisofs', "pinned libisofs source path")
    require(helper, '"submodule", "update"', "lazy submodule initialization")
    require(helper, "LIBISOFS_GIT_COMMIT=", "libisofs cache revision identity")
    require(helper, 'PKG_NAME = "libisofs-1"', "pkg-config identity")
    require(helper, '"-Werror=strict-prototypes"', "strict prototype probe")
    require(
        helper,
        'platform.system() != "Darwin"',
        "physical Darwin bootstrap guard",
    )
    require(helper, "#include <sys/types.h>", "strict-prototype POSIX types")
    require(helper, "#include <time.h>", "strict-prototype time types")
    require(helper, '"--disable-shared"', "static-only fork bootstrap")
    require(helper, '"--enable-static"', "static fork bootstrap")
    require(helper, '"--disable-libjte"', "minimal libisofs bootstrap")
    require(helper, 'LIBISOFS_BOOTSTRAP_SCHEMA = "5"', "bootstrap schema")
    require(helper, "def select_config_shell(", "configuration shell selector")
    require(helper, 'env["CONFIG_SHELL"] = config_shell', "CONFIG_SHELL routing")
    require(helper, 'env["SHELL"] = config_shell', "make shell routing")
    require(helper, 'env.pop("LIBTOOL", None)', "project-local Libtool isolation")
    require(helper, 'local_libtool = object_dir / "libtool"', "local Libtool check")
    require(helper, '[config_shell, "bootstrap"]', "bootstrap interpreter")
    require(helper, "def libisofs_link_probe(", "consumer link probe")
    require(
        helper,
        'iso_set_local_charset((char *) "UTF-8", 0);',
        "minimum-version iconv link probe",
    )
    if "iso_conv_name_chars(" in helper:
        raise SystemExit(
            "error: libisofs link probe raises the declared >=1.1.2 API minimum"
        )
    require(helper, "def find_static_library(", "static archive cache guard")
    require(helper, '"-lz" not in static_flags', "zlib static dependency check")
    require(
        helper,
        '"-lpthread" not in static_flags',
        "pthread static dependency check",
    )
    require(helper, "def select_gnu_libtool(", "GNU Libtool selector")
    require(helper, '"GNU libtool" in version', "GNU Libtool validation")
    if '("glibtool", "libtool")' in helper:
        raise SystemExit(
            "error: libisofs bootstrap still selects a global libtool driver"
        )
    require(
        helper,
        '("glibtoolize", "libtoolize")',
        "macOS GNU libtoolize preference",
    )
    require(
        helper,
        'env["LIBTOOLIZE"] = libtoolize',
        "explicit libtoolize bootstrap handoff",
    )
    if 'libtool_arg = f"LIBTOOL={libtool}"' in helper:
        raise SystemExit(
            "error: libisofs still overrides its generated project-local libtool"
        )
    require(
        helper,
        'env.pop("INSTALL", None)',
        "WHP INSTALL policy isolation from Autoconf",
    )
    require(
        helper,
        'libtool --mode=install 1',
        "documented INSTALL collision regression",
    )
    require(helper, "WHP_INCREMENTAL_BUILD", "incremental libisofs policy")
    require(helper, "def prepare_workspace(", "incremental workspace planner")
    require(helper, ".whp-libisofs-workspace", "workspace identity marker")

    if libisofs_util:
        require(
            libisofs_util,
            "char *iso_local_make_abspath(const char *path)",
            "local path namespace anchor",
        )
        require(
            libisofs_util,
            "if (path[0] == '/' || path[0] == 0)",
            "absolute host-path preservation",
        )
    if libisofs_data_source:
        require(
            libisofs_data_source,
            "absolute_path = iso_local_make_abspath(path);",
            "data-source path anchoring",
        )
        require(
            libisofs_data_source,
            "data->path = absolute_path;",
            "anchored data-source path ownership",
        )
    if libisofs_fs_local:
        require(
            libisofs_fs_local,
            "absolute_path = iso_local_make_abspath(path);",
            "local-filesystem path anchoring",
        )
        require(
            libisofs_fs_local,
            "if (child == NULL)",
            "root dot-dot guard",
        )

    require(
        meson,
        "dependency('libisofs-1', version: '>=1.1.2'",
        "QEMU libisofs dependency contract",
    )
    require(
        meson,
        "name: 'libisofs strict prototypes'",
        "Meson strict-prototype compile probe",
    )
    require(meson, "#include <sys/types.h>", "Meson libisofs POSIX types")
    require(meson, "#include <time.h>", "Meson libisofs time types")
    require(
        meson,
        "libisofs.h is incompatible with -Wstrict-prototypes",
        "forced dependency diagnostic",
    )

    require(workflow, "autoconf automake", "Autotools CI dependencies")
    require(workflow, "libtool", "libtool CI dependency")
    if "glib libisofs libslirp" in workflow:
        raise SystemExit(
            "error: native macOS CI still installs Homebrew libisofs instead "
            "of exercising the pinned WHP fork"
        )

    test_incremental_workspace()
    print("WHP libisofs bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
