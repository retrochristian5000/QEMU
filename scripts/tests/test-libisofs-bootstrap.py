#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import os
import stat
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
printf '%s\\n' "gm4: unrecognized option '--gnu'" >&2
exit 1
"""
    path.write_text(body, encoding="utf-8")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def test_gnu_m4_selector() -> None:
    helper = load_helper_module()
    with tempfile.TemporaryDirectory(prefix="whp-libisofs-m4-") as tmp:
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
                        "error: invalid libisofs M4 diagnostic lost capability detail"
                    )
            else:
                raise SystemExit("error: libisofs accepted non-GNU M4")

            os.environ["M4"] = str(good)
            if helper.select_gnu_m4() != str(good):
                raise SystemExit("error: libisofs did not honor explicit GNU M4")
        finally:
            if old_m4 is None:
                os.environ.pop("M4", None)
            else:
                os.environ["M4"] = old_m4


def test_autotools_utility_isolation() -> None:
    helper = load_helper_module()
    env = {name: f"poison-{name}" for name in helper.AUTOTOOLS_UTILITY_ENV}
    env.update(
        {
            "AR": "/managed/llvm-ar",
            "RANLIB": "/managed/llvm-ranlib",
            "NM": "/managed/llvm-nm",
            "STRIP": "/managed/llvm-strip",
            "SED": "/managed/sed",
        }
    )
    helper.isolate_autotools_utility_env(env)
    leaked = [name for name in helper.AUTOTOOLS_UTILITY_ENV if name in env]
    if leaked:
        raise SystemExit(
            "error: libisofs retained caller Autotools utility overrides: "
            + ", ".join(leaked)
        )
    for name in ("AR", "RANLIB", "NM", "STRIP", "SED"):
        if name not in env:
            raise SystemExit(
                f"error: libisofs utility isolation erased intentional {name}"
            )


def test_dependency_flag_isolation() -> None:
    helper = load_helper_module()
    env = {name: f"poison-{name}" for name in helper.DEPENDENCY_FLAG_ENV}
    env.update({
        "AR": "/managed/llvm-ar",
        "RANLIB": "/managed/llvm-ranlib",
        "NM": "/managed/llvm-nm",
        "STRIP": "/managed/llvm-strip",
        "LIPO": "/managed/llvm-lipo",
    })
    helper.isolate_dependency_flag_env(env)
    leaked = [name for name in helper.DEPENDENCY_FLAG_ENV if name in env]
    if leaked:
        raise SystemExit(
            "error: libisofs retained caller compiler/linker policy: "
            + ", ".join(leaked)
        )
    for name in ("AR", "RANLIB", "NM", "STRIP", "LIPO"):
        if name not in env:
            raise SystemExit(
                f"error: libisofs flag isolation erased intentional {name}"
            )

def test_c_standard_policy() -> None:
    helper = load_helper_module()
    if helper.LIBISOFS_C_STANDARD != "gnu11":
        raise SystemExit(
            "error: libisofs bootstrap must follow QEMU GNU C11 policy"
        )
    expected = ["-std=gnu11", "-Werror=strict-prototypes"]
    if helper.libisofs_c_policy_flags() != expected:
        raise SystemExit(
            "error: libisofs GNU C compiler policy flags drifted"
        )


def test_qemu_bootstrap_source_pruning() -> None:
    helper = load_helper_module()
    with tempfile.TemporaryDirectory(prefix="whp-libisofs-prune-") as tmp:
        source = Path(tmp)
        for directory in helper.QEMU_UNUSED_SOURCE_DIRS:
            path = source / directory
            path.mkdir(parents=True, exist_ok=True)
            (path / "unused").write_text("unused\n", encoding="utf-8")
        for filename in helper.QEMU_UNUSED_SOURCE_FILES:
            path = source / filename
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("unused\n", encoding="utf-8")

        for filename in ("configure", "Makefile.in", "configure.ac", "Makefile.am", "acinclude.m4"):
            (source / filename).write_text("keep\n", encoding="utf-8")
        (source / "libisofs").mkdir()
        (source / "libisofs/core.c").write_text("keep\n", encoding="utf-8")

        helper.prune_qemu_bootstrap_source(source)

        for directory in helper.QEMU_UNUSED_SOURCE_DIRS:
            if (source / directory).exists():
                raise SystemExit(
                    f"error: QEMU libisofs bootstrap retained {directory}"
                )
        for filename in helper.QEMU_UNUSED_SOURCE_FILES:
            if (source / filename).exists():
                raise SystemExit(
                    f"error: QEMU libisofs bootstrap retained {filename}"
                )
        for filename in ("configure", "Makefile.in", "configure.ac", "Makefile.am", "acinclude.m4"):
            if not (source / filename).is_file():
                raise SystemExit(
                    f"error: QEMU libisofs bootstrap pruned required {filename}"
                )
        if not (source / "libisofs/core.c").is_file():
            raise SystemExit("error: QEMU libisofs bootstrap pruned library source")

def test_private_install_surface_contract() -> None:
    helper = load_helper_module()
    with tempfile.TemporaryDirectory(prefix="whp-libisofs-install-") as tmp:
        prefix = Path(tmp)
        (prefix / "lib").mkdir()
        (prefix / "lib/libisofs.a").write_bytes(b"archive")
        (prefix / "include/libisofs").mkdir(parents=True)
        (prefix / "include/libisofs/libisofs.h").write_text(
            "/* header */\n", encoding="utf-8"
        )
        (prefix / "lib/pkgconfig").mkdir()
        (prefix / "lib/pkgconfig/libisofs-1.pc").write_text(
            "Version: 1.5.9\n", encoding="utf-8"
        )
        (prefix / "lib/libisofs.la").write_text("metadata\n", encoding="utf-8")
        helper.prune_private_install_metadata(prefix)
        if (prefix / "lib/libisofs.la").exists():
            raise SystemExit("error: private libisofs install retained .la metadata")
        helper.verify_private_install_surface(prefix)

        (prefix / "share/doc/libisofs/doc/html").mkdir(parents=True)
        try:
            helper.verify_private_install_surface(prefix)
        except RuntimeError as exc:
            if "non-private artifacts" not in str(exc):
                raise SystemExit(
                    "error: private-install rejection lost artifact detail"
                )
        else:
            raise SystemExit(
                "error: private libisofs install accepted documentation output"
            )

def test_macho_archive_architecture_contract() -> None:
    helper = load_helper_module()
    archive = Path("/tmp/libisofs.a")
    with mock.patch.object(helper.platform, "system", return_value="Darwin"):
        with mock.patch.object(
            helper, "select_macho_lipo", return_value="/managed/llvm-lipo"
        ):
            with mock.patch.object(
                helper, "run_text", return_value="arm64e \n"
            ) as run_text_mock:
                helper.verify_macho_archive_architecture(archive, "arm64e")
                run_text_mock.assert_called_once_with(
                    ["/managed/llvm-lipo", "-archs", str(archive)]
                )

            with mock.patch.object(
                helper, "run_text", return_value="arm64 arm64e \n"
            ):
                try:
                    helper.verify_macho_archive_architecture(archive, "arm64e")
                except RuntimeError as exc:
                    if "expected only arm64e" not in str(exc):
                        raise SystemExit(
                            "error: mixed-architecture libisofs diagnostic lost ABI detail"
                        )
                else:
                    raise SystemExit(
                        "error: mixed-architecture libisofs archive was accepted"
                    )

            with mock.patch.object(
                helper, "run_text", return_value="arm64 \n"
            ):
                try:
                    helper.verify_macho_archive_architecture(archive, "arm64e")
                except RuntimeError:
                    pass
                else:
                    raise SystemExit(
                        "error: arm64 archive was accepted for arm64e"
                    )

def test_macos_deployment_contract() -> None:
    helper = load_helper_module()
    base_env = {
        "SDKROOT": "/tmp/whp-fake-macos-sdk",
        "WHP_MACOS_ARCH": "arm64e",
        "MACOSX_DEPLOYMENT_TARGET": "10.15",
    }
    with mock.patch.object(helper.platform, "system", return_value="Darwin"):
        with mock.patch.dict(os.environ, base_env, clear=False):
            try:
                helper.macos_settings()
            except RuntimeError as exc:
                if ">= 11.0" not in str(exc):
                    raise SystemExit(
                        "error: invalid arm64e deployment diagnostic lost ABI detail"
                    )
            else:
                raise SystemExit(
                    "error: libisofs accepted pre-11.0 arm64e deployment target"
                )

        base_env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
        with mock.patch.dict(os.environ, base_env, clear=False):
            _, arch, deployment = helper.macos_settings()
            if arch != "arm64e" or deployment != "11.0":
                raise SystemExit(
                    "error: valid arm64e deployment target was not preserved"
                )

        base_env["MACOSX_DEPLOYMENT_TARGET"] = "11"
        with mock.patch.dict(os.environ, base_env, clear=False):
            _, arch, deployment = helper.macos_settings()
            if arch != "arm64e" or deployment != "11":
                raise SystemExit(
                    "error: major-only arm64e deployment target was rejected"
                )

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
    libisofs_bootstrap = (
        (libisofs_root / "bootstrap").read_text(encoding="utf-8")
        if (libisofs_root / "bootstrap").is_file() else ""
    )
    libisofs_configure = (
        (libisofs_root / "configure.ac").read_text(encoding="utf-8")
        if (libisofs_root / "configure.ac").is_file() else ""
    )
    libisofs_acinclude = (
        (libisofs_root / "acinclude.m4").read_text(encoding="utf-8")
        if (libisofs_root / "acinclude.m4").is_file() else ""
    )
    libisofs_makefile = (
        (libisofs_root / "Makefile.am").read_text(encoding="utf-8")
        if (libisofs_root / "Makefile.am").is_file() else ""
    )
    automake_root = ROOT / "toolchains" / "automake"
    automake_data = (
        (automake_root / "lib/am/data.am").read_text(encoding="utf-8")
        if (automake_root / "lib/am/data.am").is_file() else ""
    )
    automake_ltlib = (
        (automake_root / "lib/am/ltlib.am").read_text(encoding="utf-8")
        if (automake_root / "lib/am/ltlib.am").is_file() else ""
    )
    automake_driver = (
        (automake_root / "bin/automake.in").read_text(encoding="utf-8")
        if (automake_root / "bin/automake.in").is_file() else ""
    )
    autoconf_c = (
        (ROOT / "toolchains/autoconf/lib/autoconf/c.m4").read_text(
            encoding="utf-8"
        )
        if (ROOT / "toolchains/autoconf/lib/autoconf/c.m4").is_file() else ""
    )
    libisofs_node_header = (
        (libisofs_root / "libisofs/node.h").read_text(encoding="utf-8")
        if (libisofs_root / "libisofs/node.h").is_file() else ""
    )
    libisofs_node_source = (
        (libisofs_root / "libisofs/node.c").read_text(encoding="utf-8")
        if (libisofs_root / "libisofs/node.c").is_file() else ""
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
    require(
        helper,
        'LIBISOFS_C_STANDARD = "gnu11"',
        "libisofs GNU C standard",
    )
    require(
        helper,
        "def libisofs_c_policy_flags(",
        "shared libisofs GNU C compiler policy",
    )
    require(
        helper,
        'compile_flags = ["-O3", *libisofs_c_policy_flags()]',
        "libisofs GNU C build policy",
    )
    require(
        helper,
        "*libisofs_c_policy_flags(),",
        "libisofs GNU C probe policy",
    )
    if '"-std=gnu11",' in helper:
        raise SystemExit(
            "error: libisofs bootstrap still hard-codes GNU C11 outside "
            "the shared compiler policy"
        )
    require(helper, '"-Werror=strict-prototypes"', "strict prototype policy")
    require(
        helper,
        'platform.system() != "Darwin"',
        "physical Darwin bootstrap guard",
    )
    require(helper, "#include <sys/types.h>", "strict-prototype POSIX types")
    require(helper, "#include <time.h>", "strict-prototype time types")
    require(helper, '_Static_assert(sizeof(off_t) == 8', "Darwin off_t ABI guard")
    require(helper, '_Static_assert(sizeof(time_t) == 8', "Darwin time_t ABI guard")
    require(helper, '_Static_assert(sizeof(ino_t) == 8', "Darwin inode ABI guard")
    require(helper, 'sizeof(iso_node_xinfo_func) == sizeof(void *)', "function-pointer ABI guard")
    require(helper, '__has_feature(ptrauth_calls)', "arm64e consumer PAC guard")
    require(helper, '"--disable-shared"', "static-only fork bootstrap")
    require(helper, '"--enable-static"', "static fork bootstrap")
    require(helper, '"--disable-demo"', "library-only libisofs bootstrap")
    require(helper, '"--disable-docs"', "documentation-free libisofs bootstrap")
    require(helper, '"--disable-xattr"', "QEMU xattr probe disable")
    require(helper, '"--disable-lfa-flags"', "QEMU Linux attribute disable")
    require(helper, '"--disable-projid"', "QEMU project-id disable")
    require(helper, '"--disable-dir-rec-size-check"', "QEMU directory-size debug disable")
    require(helper, '"--disable-debug"', "QEMU release CFLAGS policy")
    require(helper, '"install-libLTLIBRARIES"', "library install target")
    require(helper, '"install-libincludeHEADERS"', "header install target")
    require(helper, '"install-pkgconfigDATA"', "pkg-config install target")
    if '[make, "install"]' in helper:
        raise SystemExit("error: libisofs helper regressed to blanket make install")
    require(
        helper,
        '"--disable-versioned-libs"',
        "static build source-path isolation",
    )
    require(helper, '"--disable-libjte"', "minimal libisofs bootstrap")
    require(helper, 'LIBISOFS_BOOTSTRAP_SCHEMA = "13"', "bootstrap schema")
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
    require(helper, "def select_automake_pair(", "GNU Automake pair selector")
    require(helper, "def select_autoconf(", "GNU Autoconf selector")
    require(
        helper,
        'raise RuntimeError("AUTOMAKE and ACLOCAL must be supplied as a pair")',
        "Automake/aclocal pair admission",
    )
    require(
        helper,
        "if automake_version != aclocal_version:",
        "Automake/aclocal version coherence",
    )
    require(
        helper,
        "GNU Autoconf 2.69 or newer is required by libisofs",
        "Autoconf minimum-version guard",
    )
    require(helper, 'env["AUTOMAKE"] = automake', "Automake bootstrap handoff")
    require(helper, 'env["ACLOCAL"] = aclocal', "aclocal bootstrap handoff")
    require(helper, 'env["AUTOCONF"] = autoconf', "Autoconf bootstrap handoff")
    require(helper, 'env["ACLOCAL_PATH"] = ""', "aclocal macro-path isolation")
    require(helper, 'f"AUTOMAKE_VERSION={automake_version}\\n"', "Automake cache identity")
    require(helper, 'f"AUTOCONF_VERSION={autoconf_version}\\n"', "Autoconf cache identity")
    require(helper, '"ACLOCAL_PATH=ISOLATED\\n"', "aclocal cache identity")
    require(helper, "def select_gnu_libtool(", "GNU Libtool selector")
    require(helper, "def select_gnu_m4(", "GNU M4 selector")
    require(helper, '"--gnu", "--version"', "GNU M4 capability probe")
    require(helper, 'env["M4"] = m4', "GNU M4 Autotools handoff")
    require(helper, 'f"M4={m4}\\n"', "GNU M4 workspace identity")
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
        "AUTOTOOLS_UTILITY_ENV = (",
        "Autotools utility isolation set",
    )
    require(
        helper,
        "DEPENDENCY_FLAG_ENV = (",
        "dependency compiler/linker flag isolation set",
    )
    require(
        helper,
        "def isolate_dependency_flag_env(",
        "dependency compiler/linker flag isolation helper",
    )
    require(
        helper,
        "isolate_dependency_flag_env(env)",
        "dependency compiler/linker flag isolation application",
    )
    require(helper, 'env["CFLAGS"] = " ".join(compile_flags)', "owned CFLAGS")
    require(helper, 'env["CPPFLAGS"] = ""', "isolated CPPFLAGS")
    require(helper, 'env["LDFLAGS"] = ""', "isolated LDFLAGS")
    require(helper, '"CXXFLAGS=UNUSED\\n"', "C++ flag non-participation marker")
    require(helper, '"LINKER_POLICY=COMPILER_DEFAULT\\n"', "linker policy marker")
    if "append_flags(" in helper:
        raise SystemExit("error: libisofs still appends QEMU caller flags")
    if "link_flags=architecture_flags" in helper:
        raise SystemExit("error: libisofs duplicates Darwin ABI flags at link")
    require(
        helper,
        "def isolate_autotools_utility_env(",
        "Autotools utility isolation helper",
    )
    require(
        helper,
        "isolate_autotools_utility_env(env)",
        "Autotools utility isolation application",
    )
    require(helper, 'env["SED"] = sed', "explicit sed handoff")
    require(helper, 'f"SED={sed}\\n"', "sed workspace identity")
    require(
        helper,
        '    "INSTALL",',
        "INSTALL command-variable isolation",
    )
    require(helper, "WHP_INCREMENTAL_BUILD", "incremental libisofs policy")
    require(helper, "def prepare_workspace(", "incremental workspace planner")
    require(helper, ".whp-libisofs-workspace", "workspace identity marker")
    require(helper, "verify_private_install_surface(prefix)", "cache install-surface admission")
    require(helper, "def verify_macho_archive_architecture(", "Mach-O ABI verifier")
    require(helper, '"-archs", str(archive)', "archive-safe llvm-lipo architecture query")
    if "\"-verify_arch\"" in helper:
        raise SystemExit("error: libisofs helper still uses llvm-lipo -verify_arch on archives")
    require(helper, 'deployment_version[0] < 11', "Apple-silicon deployment guard")

    if libisofs_bootstrap:
        if "uname -s" in libisofs_bootstrap:
            raise SystemExit(
                "error: libisofs bootstrap still spawns uname to choose libtoolize"
            )
        require(
            libisofs_bootstrap,
            "command -v glibtoolize",
            "glibtoolize capability-based selection",
        )
        require(libisofs_bootstrap, 'ACLOCAL=${ACLOCAL:-aclocal}', "explicit aclocal selection")
        require(libisofs_bootstrap, 'AUTOCONF=${AUTOCONF:-autoconf}', "explicit Autoconf selection")
        require(libisofs_bootstrap, 'AUTOMAKE=${AUTOMAKE:-automake}', "explicit Automake selection")
        require(libisofs_bootstrap, "ACLOCAL_PATH=", "aclocal macro-path isolation")
        require(libisofs_bootstrap, '"$ACLOCAL" -I .', "selected aclocal invocation")
        require(libisofs_bootstrap, '"$AUTOCONF"', "selected Autoconf invocation")
        require(libisofs_bootstrap, '"$AUTOMAKE" --foreign', "selected Automake invocation")
        if "\naclocal -I .\n" in libisofs_bootstrap:
            raise SystemExit("error: libisofs bootstrap still invokes bare aclocal")
        if "\nautoconf\n" in libisofs_bootstrap:
            raise SystemExit("error: libisofs bootstrap still invokes bare autoconf")
        if "\nautomake --foreign" in libisofs_bootstrap:
            raise SystemExit("error: libisofs bootstrap still invokes bare automake")
    if libisofs_configure:
        require(
            libisofs_configure,
            "LT_CURRENT_MINUS_AGE=$((LT_CURRENT - LT_AGE))",
            "shell-native Libtool version arithmetic",
        )
        require(
            libisofs_configure,
            "libisofs_cv_darwin_abi64",
            "64-bit Darwin ABI configure probe",
        )
        require(
            libisofs_configure,
            "sizeof(ino_t) == 8",
            "Darwin ino_t width configure guard",
        )
        require(
            libisofs_configure,
            "LIBISOFS_DARWIN_ABI64",
            "validated Darwin ABI define",
        )
        require(
            libisofs_configure,
            "AC_ARG_ENABLE([demo],",
            "optional libisofs demo configure switch",
        )
        require(
            libisofs_configure,
            "AM_CONDITIONAL([BUILD_DEMO]",
            "libisofs demo Automake conditional",
        )
        require(
            libisofs_configure,
            "AC_ARG_ENABLE([docs],",
            "optional libisofs documentation configure switch",
        )
        require(
            libisofs_configure,
            "AM_CONDITIONAL([BUILD_DOCS]",
            "libisofs documentation Automake conditional",
        )
        require(
            libisofs_configure,
            'AS_IF([test "x$enable_docs" = xyes]',
            "conditional Doxygen configure output",
        )
        require(
            libisofs_configure,
            "libisofs_user_cflags_set != xyes",
            "caller-owned CFLAGS policy guard",
        )
        require(
            libisofs_configure,
            "CFLAGS=\"-DNDEBUG $CFLAGS\"",
            "release semantic define",
        )
        if "expr $LT_CURRENT - $LT_AGE" in libisofs_configure:
            raise SystemExit(
                "error: libisofs still uses external expr for version arithmetic"
            )
    if libisofs_acinclude:
        require(
            libisofs_acinclude,
            '${libdir%/lib}/libdata/pkgconfig',
            "shell-native FreeBSD pkg-config path rewrite",
        )
        if "printf '%s\\n' \"$libdir\" | \"$SED\"" in libisofs_acinclude:
            raise SystemExit(
                "error: libisofs still spawns sed for a simple /lib suffix rewrite"
            )
    if libisofs_makefile:
        require(
            libisofs_makefile,
            "if BUILD_DEMO",
            "conditional demo build graph",
        )
        require(
            libisofs_makefile,
            "if BUILD_DOCS",
            "conditional documentation build graph",
        )
        require(
            libisofs_makefile,
            "doc:\tdoc/html",
            "documentation target remains standalone-only",
        )
        require(
            libisofs_makefile,
            "noinst_PROGRAMS =",
            "conditional demo program declaration",
        )
        require(
            libisofs_makefile,
            "demo/demo",
            "conditional demo program target",
        )
        require(
            libisofs_makefile,
            "-$(RM) -r demo/.libs",
            "Automake cleanup utility",
        )
        require(
            libisofs_makefile,
            '$(MKDIR_P) "$(docdir)/html"',
            "Automake directory creation utility",
        )
        require(
            libisofs_makefile,
            '$(RM) -r "$(docdir)"',
            "Automake uninstall cleanup utility",
        )
        if "$(mkinstalldirs)" in libisofs_makefile:
            raise SystemExit(
                "error: libisofs still uses deprecated mkinstalldirs"
            )
    if libisofs_node_header:
        require(
            libisofs_node_header,
            "iso_node_xinfo_func process;",
            "typed xinfo function-pointer storage",
        )
    if libisofs_node_source:
        require(
            libisofs_node_source,
            "info->process = proc;",
            "typed xinfo function-pointer assignment",
        )
        require(
            libisofs_node_source,
            "pos->process == proc",
            "typed xinfo function-pointer comparison",
        )
    if automake_ltlib:
        require(
            automake_ltlib,
            "install-%DIR%LTLIBRARIES:",
            "Automake Libtool install target template",
        )
        require(
            automake_ltlib,
            "--mode=install $(INSTALL)",
            "Automake Libtool installer contract",
        )
    if automake_data:
        require(
            automake_data,
            "install-%DIR%%PRIMARY%:",
            "Automake data/header install target template",
        )
    if automake_driver:
        require(
            automake_driver,
            "'link' => '$(CCLD) $(AM_CFLAGS) $(CFLAGS) $(AM_LDFLAGS) $(LDFLAGS) -o $@'",
            "Automake C link carries CFLAGS",
        )
    if autoconf_c:
        require(
            autoconf_c,
            "char $2 (void);",
            "Autoconf AC_CHECK_LIB strict prototype",
        )
        require(
            autoconf_c,
            "char $1 (void);",
            "Autoconf AC_CHECK_FUNC strict prototype",
        )

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

    test_gnu_m4_selector()
    test_autotools_utility_isolation()
    test_dependency_flag_isolation()
    test_c_standard_policy()
    test_qemu_bootstrap_source_pruning()
    test_private_install_surface_contract()
    test_macho_archive_architecture_contract()
    test_macos_deployment_contract()
    test_incremental_workspace()
    print("WHP libisofs bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
