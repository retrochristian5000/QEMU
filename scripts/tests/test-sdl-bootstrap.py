#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    build += (ROOT / "scripts/whp-build/host-libraries.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-sdl.py").read_text(encoding="utf-8")
    meson = (ROOT / "meson.build").read_text(encoding="utf-8")
    builder = (ROOT / "builder.bash").read_text(encoding="utf-8")
    macos_builder = (ROOT / "scripts/macos-builder.bash").read_text(
        encoding="utf-8"
    )
    portable = (ROOT / "scripts/whp-build/portable-build.py").read_text(
        encoding="utf-8"
    )

    require(gitmodules, '[submodule "toolchains/sdl"]', "SDL submodule declaration")
    require(gitmodules, "path = toolchains/sdl", "SDL submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/SDLosaurus.git",
        "WHP SDL fork URL",
    )
    require(gitmodules, "branch = main", "SDL fork branch")

    require(
        config,
        "Option('BOOTSTRAP_SDL', 'Host features', 'Bootstrap/use WHP SDL3', "
        "'choice', 'auto', ('auto', 'y', 'n'))",
        "menuconfig SDL bootstrap policy",
    )
    require(config, "'BOOTSTRAP_SDL',", "SDL tri-state shell export")

    require(build, "BOOTSTRAP_SDL=${BOOTSTRAP_SDL:-auto}", "SDL bootstrap default")
    require(build, 'scripts/ensure-sdl.py', "SDL bootstrap hook")
    require(build, 'SDL_BOOTSTRAP_MODE=force', "forced SDL fork policy")
    require(build, 'PKG_CONFIG_PATH=', "SDL pkg-config handoff")
    require(build, 'CMAKE_PREFIX_PATH=', "SDL CMake handoff")
    require(build, 'SDL3_ROOT=', "SDL prefix identity handoff")

    require(helper, 'toolchains/sdl', "pinned SDL source path")
    require(helper, '"submodule",', "lazy SDL submodule initialization")
    require(helper, 'SDL_GIT_COMMIT=', "SDL cache revision identity")
    require(helper, 'SDL_BOOTSTRAP_SCHEMA', "SDL bootstrap cache schema")
    require(helper, '"--atleast-version=3.2.0"', "host SDL3 minimum version probe")
    require(helper, '"-DSDL_SHARED=ON"', "dynamic SDL3 bootstrap")
    require(helper, '"-DSDL_STATIC=OFF"', "disable static SDL3 archives")
    require(helper, '"-DCMAKE_INSTALL_LIBDIR=lib"', "shared SDL3 lib location")
    require(helper, 'SDL_BOOTSTRAP_SCHEMA = "3"', "SDL ObjC compatibility cache invalidation")
    require(helper, '"-DSDL_OBJC_NO_CLASS_SELECTOR_STUBS=ON"',
            "SDL source-specific class-stub fallback option")
    if "-DCMAKE_OBJC_FLAGS=-fno-objc-msgsend-class-selector-stubs" in helper:
        raise SystemExit(
            "error: SDL class-stub mitigation is scoped to Apple .m files, not CMake OBJC flags"
        )
    require(helper, 'and os.environ.get("NATIVE_LLVM_LDFLAG") == "-fuse-ld=lld"',
            "only disable Objective-C class stubs for selected LLD")
    require(helper, "find_shared_sdl(prefix)", "verify installed shared SDL3 artifact")
    require(helper, '"-DSDL_INSTALL=ON"', "SDL install staging")
    require(helper, 'CMAKE_MAKE_PROGRAM', "selected Ninja handoff to SDL CMake")

    require(
        meson,
        "dependency('sdl3', version: '>=3.2.0'",
        "QEMU SDL3 dependency contract",
    )
    require(build, 'DYLD_FALLBACK_LIBRARY_PATH=', "macOS SDL runtime lookup")
    require(build, 'LD_LIBRARY_PATH=', "POSIX SDL runtime lookup")
    require(
        macos_builder,
        'whp_append_colon_path PKG_CONFIG_PATH "$WHP_SDL_PREFIX/lib/pkgconfig"',
        "restore private SDL pkg-config after macOS sanitation",
    )
    require(
        macos_builder,
        'whp_append_colon_path DYLD_FALLBACK_LIBRARY_PATH "$WHP_SDL_PREFIX/lib"',
        "restore private SDL runtime path after macOS sanitation",
    )
    require(helper, 'system.startswith(("MINGW", "MSYS", "CYGWIN"))',
            "MSYS and MinGW SDL3 DLL discovery")
    for path in (builder, portable):
        require(path, "@loader_path/deps/sdl3/lib", "macOS SDL load rpath")
        require(path, "$ORIGIN/deps/sdl3/lib", "ELF SDL load rpath")
        require(path, "../deps/sdl3/lib", "one-level QEMU module load rpath")

    # Test actual cache admission with shared and static-only fixtures.
    spec = importlib.util.spec_from_file_location(
        "whp_sdl_bootstrap", ROOT / "scripts/ensure-sdl.py"
    )
    if spec is None or spec.loader is None:
        raise SystemExit("error: cannot load SDL bootstrap helper")
    helper_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper_module)

    # Apple's ld handles new class-message stubs. Only the selected managed
    # Mach-O LLD currently needs the narrowly scoped SDL Objective-C fallback.
    native = {
        "NATIVE_LLVM_LDFLAG": "-fuse-ld=lld",
        "LD": "/private/whp/llvm/bin/ld64.lld",
    }
    for system, environment, expected in (
        ("Darwin", native, True),
        ("Darwin", {"NATIVE_LLVM_LDFLAG": "", "LD": "/usr/bin/ld"}, False),
        ("Linux", native, False),
        ("Darwin", {"NATIVE_LLVM_LDFLAG": "-fuse-ld=lld", "LD": "/usr/bin/ld"}, False),
    ):
        with mock.patch.object(helper_module.platform, "system", return_value=system):
            with mock.patch.dict(helper_module.os.environ, environment):
                assert helper_module.needs_objc_class_stub_fallback() == expected
                identity = helper_module.marker_text(
                    "revision", "cmake", "cmake-version", "ninja",
                    "ninja-version", "cc", "cc-version", "", "",
                )
                assert (
                    f"SDL_OBJC_CLASS_STUB_FALLBACK={int(expected)}" in identity
                )

    with tempfile.TemporaryDirectory() as td:
        prefix = pathlib.Path(td)
        lib = prefix / "lib"
        pc_dir = lib / "pkgconfig"
        pc_dir.mkdir(parents=True)
        (pc_dir / "sdl3.pc").write_text(
            "Name: sdl3\nVersion: 3.2.0\n", encoding="utf-8"
        )
        marker = helper_module.marker_text(
            "revision", "cmake", "cmake-version", "ninja",
            "ninja-version", "cc", "cc-version", "", "",
        )
        (prefix / ".whp-sdl-bootstrap").write_text(marker, encoding="utf-8")
        with mock.patch.object(helper_module.platform, "system", return_value="Linux"):
            assert not helper_module.cache_valid(prefix, marker), (
                "a pkg-config file alone must not validate a shared SDL3 cache"
            )
            shared = lib / "libSDL3.so.0"
            shared.write_bytes(b"nonempty test fixture")
            assert helper_module.cache_valid(prefix, marker)
            shared.unlink()
            (lib / "libSDL3.a").write_bytes(b"static fixture")
            assert not helper_module.cache_valid(prefix, marker), (
                "a static archive must not satisfy the shared SDL3 cache"
            )
        with mock.patch.object(helper_module.platform, "system", return_value="Darwin"):
            (lib / "libSDL3.0.dylib").write_bytes(b"shared fixture")
            assert helper_module.cache_valid(prefix, marker)
        for host in ("Windows", "MINGW64_NT-10.0", "MSYS_NT-10.0"):
            with mock.patch.object(helper_module.platform, "system", return_value=host):
                (prefix / "bin").mkdir(exist_ok=True)
                (prefix / "bin" / "SDL3.dll").write_bytes(b"shared fixture")
                assert helper_module.cache_valid(prefix, marker)

    print("WHP SDL3 shared bootstrap and runtime wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
