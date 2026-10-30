#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    adapter = (ROOT / "cc.sh").read_text(encoding="utf-8")
    cxx_adapter = (ROOT / "cxx.sh").read_text(encoding="utf-8")
    shared = (ROOT / "scripts/whp-build/compiler-seed-common.sh").read_text(encoding="utf-8")
    require(shared, "compiler_runs_native", "native execution probe")
    require(shared, 'whp_apple_find_sdk', "native Apple SDK seed lookup")
    require(shared, 'whp_apple_check_sdkroot "$SDKROOT"', "explicit SDK root guard")
    require(shared, 'set -- -isysroot "$seed_sdk"', "native Apple SDK link probe")
    require(shared, 'mktemp -d', "unique native probe directory")
    require(shared, 'cat "$log" >&2', "compiler stderr on failure")
    require(shared, 'executable probe failed', "native execution failure stage")
    require(shared, 'compiler --version failed', "compiler version failure stage")
    require(adapter, 'try_compiler c "$value" report', "explicit/Apple C diagnostics")
    require(cxx_adapter, 'try_compiler c++ "$value" report', "explicit/Apple C++ diagnostics")
    require(shared, "-std=c++17", "C++17 seed requirement")
    require(shared, "whp-qemu-cxx-seed-adapter", "cross-adapter recursion guard")
    require(adapter, "CC_FOR_BUILD", "C build-machine role")
    require(cxx_adapter, "CXX_FOR_BUILD", "C++ build-machine role")
    require(adapter, "use cxx.sh for C++", "C-only guard")
    require(cxx_adapter, "use cc.sh for C", "C++-only guard")
    require(adapter, "whp_apple_find_tool clang", "active Apple C selection")
    require(cxx_adapter, "whp_apple_find_tool clang++", "active Apple C++ selection")
    apple = (ROOT / "scripts/whp-build/macos-developer-tools.sh").read_text(
        encoding="utf-8"
    )
    require(apple, "DEVELOPER_DIR", "developer directory override")
    require(apple, "xcode-select -p", "active developer fallback")
    require(apple, "whp_apple_check_sdkroot", "SDK/developer root guard")
    macos = (ROOT / "scripts/macos-builder.bash").read_text(encoding="utf-8")
    require(macos, 'whp_apple_check_sdkroot "$SDKROOT"', "macOS SDK coherence")
    policy = (ROOT / "scripts/macos-compiler-policy.bash").read_text(
        encoding="utf-8"
    )
    require(policy, "whp_apple_find_tool clang++", "Apple compiler root guard")
    require(apple, '"/usr/bin/$name"', "Apple system shim support")
    require(macos, "whp_apple_find_tool ranlib system", "Apple archive tool selection")
    prepare = (ROOT / "scripts/whp-build/prepare-build.bash").read_text(
        encoding="utf-8"
    )
    require(prepare, "whp_apple_find_tool strip system", "Apple host strip selection")
    if "select_cxx()" in adapter or "select_cc()" in cxx_adapter:
        raise SystemExit("error: compiler selectors cross language roles")

    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    require(build, '"$SOURCE_DIR/cc.sh" --print-cc', "early C seed")
    require(build, "CC_FOR_BUILD=", "build-machine C handoff")

    linker = (ROOT / "ld.sh").read_text(encoding="utf-8")
    require(linker, "linker_links_native_object", "native linker object probe")
    require(linker, "WHP_LD_SEED LD_FOR_BUILD", "linker seed overrides")
    require(linker, 'exec "$seed" "$@"', "linker argument passthrough")
    require(linker, "whp_apple_find_tool ld system", "active Apple linker seed")
    require(linker, "whp_ld_root", "linker symlink root guard")
    require(linker, "Never auto-select ld64.lld", "ARM64e and ASan guard")
    require(build, '"$SOURCE_DIR/ld.sh" --print-ld', "early linker seed")
    require(build, "LD_FOR_BUILD=", "build-machine linker handoff")
    if 'LD="$SOURCE_DIR/ld.sh"' in build:
        raise SystemExit("error: bootstrap linker must not replace QEMU artifact LD")

    python = (ROOT / "scripts/bootstrap-python.sh").read_text(encoding="utf-8")
    require(python, "CC_FOR_BUILD", "Python build compiler handoff")
    require(python, '"$SOURCE_DIR/cc.sh" --print-cc', "Python adapter fallback")

    sed = (ROOT / "scripts/ensure-sed.py").read_text(encoding="utf-8")
    require(sed, 'SED_BOOTSTRAP_SCHEMA = "4"', "sed compiler/SDK cache schema")
    require(sed, "validate_configure_compiler(cc, env, work)", "sed configured CC probe")
    require(sed, 'env["SDKROOT"] = sdkroot', "sed pinned native SDK")
    require(sed, "gettext_aclocal_dir()", "sed gettext macro source")
    require(sed, 'report_configure_failure(objects / "config.log")',
            "sed configure failure diagnostics")
    require(sed, '"CONFIG_SITE"', "sed inherited site cache isolation")

    for relpath in (
        "scripts/ensure-git.py",
        "scripts/ensure-sed.py",
        "scripts/ensure-bash.py",
    ):
        text = (ROOT / relpath).read_text(encoding="utf-8")
        require(text, "CC_FOR_BUILD", f"{relpath} build compiler role")
        require(text, "cc.sh", f"{relpath} adapter fallback")

    ninja = (ROOT / "scripts/ensure-ninja.py").read_text(encoding="utf-8")
    require(ninja, "CXX_FOR_BUILD", "Ninja build C++ role")
    require(ninja, "ROOT / 'cxx.sh'", "Ninja C++ adapter")
    if "os.environ.get('CXX')" in ninja:
        raise SystemExit("error: Ninja bootstrap must not inherit target CXX")

    sdl = (ROOT / "scripts/ensure-sdl.py").read_text(encoding="utf-8")
    require(sdl, '("CC", "CC_FOR_BUILD")', "SDL artifact/build compiler priority")

    jack = (ROOT / "scripts/ensure-jack.py").read_text(encoding="utf-8")
    require(jack, 'command_path("clang", "CC"', "JACK artifact C role")
    require(jack, 'command_path("clang++", "CXX"', "JACK artifact C++ role")
    require(jack, '"CC_FOR_BUILD"', "JACK C fallback")
    require(jack, '"CXX_FOR_BUILD"', "JACK C++ fallback")
    require(jack, '"cc.sh" if env_name == "CC" else "cxx.sh"', "JACK split")

    llvm = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(encoding="utf-8")
    require(llvm, '"$SOURCE_DIR/cc.sh" --print-cc', "LLVM C seed")
    require(llvm, '"$SOURCE_DIR/cxx.sh" --print-cxx', "LLVM C++ seed")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "Bootstrap compiler boundary", "compiler ledger section")
    require(ledger, "cross compiler cannot leak backward", "target bleed guard")

    print("WHP bootstrap compiler policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
