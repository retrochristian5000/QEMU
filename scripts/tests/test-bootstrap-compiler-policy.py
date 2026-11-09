#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import os
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def main() -> int:
    adapter = (ROOT / "seeds" / "cc.sh").read_text(encoding="utf-8")
    cxx_adapter = (ROOT / "seeds" / "cxx.sh").read_text(encoding="utf-8")
    shared = (ROOT / "scripts/whp-build/compiler-seed-common.sh").read_text(encoding="utf-8")
    require(shared, "compiler_runs_native", "native execution probe")
    require(shared, 'whp_apple_find_sdk', "native Apple SDK seed lookup")
    require(shared, 'whp_native_sdkroot()', "shared Apple SDK identity")
    require(shared, 'whp_apple_check_sdkroot "$SDKROOT"', "explicit SDK root guard")
    require(shared, 'set -- -isysroot "$seed_sdk"', "native Apple SDK link probe")
    require(shared, 'mktemp -d', "unique native probe directory")
    require(shared, '#include <unistd.h>', "native POSIX SDK header probe")
    require(shared, 'access(".", F_OK)', "real libc link/run probe")
    require(shared, 'unset CPATH C_INCLUDE_PATH', "probe-only include isolation")
    require(shared, 'whp_native_probe_environment', "shared compiler probe sanitation")
    require(shared, 'unset LIBRARY_PATH LD_LIBRARY_PATH', "probe-only library isolation")
    require(shared, 'candidate=$dir/', "absolute bootstrap compiler identity")
    if '/*) ;;' in shared:
        raise SystemExit("error: absolute compiler seed path bypasses physical canonicalization")
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
    require(adapter, 'seed_sdk=$(whp_native_sdkroot)', "real C compiler SDK validation")
    require(adapter, 'exec "$compiler" -isysroot "$seed_sdk" "$@"',
            "real C compiler uses validated SDK")
    require(cxx_adapter, 'exec "$compiler" -isysroot "$seed_sdk" "$@"',
            "real C++ compiler uses validated SDK")
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
    require(build, '"$SOURCE_DIR/seeds/cc.sh" --print-cc', "early C seed")
    require(build, "CC_FOR_BUILD=", "build-machine C handoff")

    linker = (ROOT / "seeds" / "ld.sh").read_text(encoding="utf-8")
    require(linker, "linker_links_native_object", "native linker object probe")
    require(linker, "WHP_LD_SEED LD_FOR_BUILD", "linker seed overrides")
    require(linker, 'exec "$seed" "$@"', "linker argument passthrough")
    require(linker, "whp_apple_find_tool ld system", "active Apple linker seed")
    require(linker, "whp_ld_root", "linker symlink root guard")
    require(linker, "Never auto-select ld64.lld", "ARM64e and ASan guard")
    require(build, '"$SOURCE_DIR/seeds/ld.sh" --print-ld', "early linker seed")
    require(build, "LD_FOR_BUILD=", "build-machine linker handoff")
    if 'LD="$SOURCE_DIR/seeds/ld.sh"' in build:
        raise SystemExit("error: bootstrap linker must not replace QEMU artifact LD")

    python = (ROOT / "scripts/bootstrap-python.sh").read_text(encoding="utf-8")
    require(python, "CC_FOR_BUILD", "Python build compiler handoff")
    require(python, '"$SOURCE_DIR/seeds/cc.sh" --print-cc', "Python adapter fallback")

    sed = (ROOT / "scripts/ensure-sed.py").read_text(encoding="utf-8")
    require(sed, 'SED_BOOTSTRAP_SCHEMA = "5"', "sed compiler/SDK/gettext cache schema")
    require(sed, "validate_configure_compiler(cc, env, work)", "sed configured CC probe")
    require(sed, 'env["SDKROOT"] = sdkroot', "sed pinned native SDK")
    require(sed, 'gettext_aclocal_dir(autopoint)', "optional external gettext macros")
    require(sed, "require_staged_gettext_macro(source)",
            "staged gettext macro prerequisite")
    require(sed, 'env["AUTOPOINT"] = autopoint',
            "selected autopoint propagated to source bootstrap")
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
    require(ninja, "ROOT / 'seeds' / 'cxx.sh'", "Ninja C++ adapter")
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
    require(llvm, '"$SOURCE_DIR/seeds/cc.sh" --print-cc', "LLVM C seed")
    require(llvm, '"$SOURCE_DIR/seeds/cxx.sh" --print-cxx', "LLVM C++ seed")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "Bootstrap compiler boundary", "compiler ledger section")
    require(ledger, "cross compiler cannot leak backward", "target bleed guard")

    # A native C seed selected explicitly must never be paired silently with
    # an unrelated Apple C++ driver if its sibling fails C++17 admission.
    with tempfile.TemporaryDirectory(prefix="whp-cxx-pair-") as tmp:
        fixture = pathlib.Path(tmp)
        (fixture / "seeds").mkdir()
        shared_dir = fixture / "scripts" / "whp-build"
        shared_dir.mkdir(parents=True)
        (fixture / "seeds" / "cxx.sh").write_text(cxx_adapter)
        (fixture / "seeds" / "cc.sh").write_text(
            '#!/bin/sh\nprintf "%s\\n" /mock/custom/clang\n'
        )
        (fixture / "seeds" / "cc.sh").chmod(0o755)
        (shared_dir / "compiler-seed-common.sh").write_text(
            'try_compiler() {\n'
            '  case "$2" in\n'
            '    /mock/custom/clang++) return 1 ;;\n'
            '    /mock/apple/clang++) printf "%s\\n" "$2" ;;\n'
            '    *) return 1 ;;\n'
            '  esac\n'
            '}\n'
        )
        (shared_dir / "macos-developer-tools.sh").write_text(
            'whp_apple_find_tool() { printf "%s\\n" /mock/apple/clang++; }\n'
        )
        commands = fixture / "commands"
        commands.mkdir()
        (commands / "uname").write_text('#!/bin/sh\nprintf "Darwin\\n"\n')
        (commands / "uname").chmod(0o755)
        env = dict(os.environ, PATH=f'{commands}:{os.environ["PATH"]}')
        for key in ("WHP_CXX_SEED", "CXX_FOR_BUILD", "WHP_CC_SEED",
                    "CC_FOR_BUILD"):
            env.pop(key, None)
        script = str(fixture / "seeds" / "cxx.sh")
        automatic = subprocess.run(["sh", script, "--print-cxx"],
                                   env=env, capture_output=True, text=True)
        assert automatic.returncode == 0, automatic.stderr
        assert automatic.stdout.strip() == "/mock/apple/clang++"
        for key in ("WHP_CC_SEED", "CC_FOR_BUILD"):
            explicit = subprocess.run(
                ["sh", script, "--print-cxx"],
                env={**env, key: "/mock/custom/clang"},
                capture_output=True, text=True)
            assert explicit.returncode != 0, (key, explicit.stdout)
            assert "no usable paired C++17 compiler" in explicit.stderr

    print("WHP bootstrap compiler policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
