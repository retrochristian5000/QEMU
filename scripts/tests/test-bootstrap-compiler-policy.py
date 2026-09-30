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
    require(adapter, "compiler_runs_native", "native execution probe")
    require(adapter, "CC_FOR_BUILD", "C build-machine role")
    require(adapter, "CXX_FOR_BUILD", "C++ build-machine role")
    require(adapter, "-std=c++17", "C++17 seed requirement")
    if 'Target/cross CC and CXX' not in adapter:
        raise SystemExit("error: cc.sh does not document target compiler exclusion")

    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    require(build, '"$SOURCE_DIR/cc.sh" --print-cc', "early C seed")
    require(build, "CC_FOR_BUILD=", "build-machine C handoff")

    python = (ROOT / "scripts/bootstrap-python.sh").read_text(encoding="utf-8")
    require(python, "CC_FOR_BUILD", "Python build compiler handoff")
    require(python, '"$SOURCE_DIR/cc.sh" --print-cc', "Python adapter fallback")

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
    require(ninja, "'--print-cxx'", "Ninja C++ adapter")
    if "os.environ.get('CXX')" in ninja:
        raise SystemExit("error: Ninja bootstrap must not inherit target CXX")

    sdl = (ROOT / "scripts/ensure-sdl.py").read_text(encoding="utf-8")
    require(sdl, '("CC", "CC_FOR_BUILD")', "SDL artifact/build compiler priority")

    jack = (ROOT / "scripts/ensure-jack.py").read_text(encoding="utf-8")
    require(jack, 'command_path("clang", "CC"', "JACK artifact C role")
    require(jack, 'command_path("clang++", "CXX"', "JACK artifact C++ role")
    require(jack, '"CC_FOR_BUILD"', "JACK C fallback")
    require(jack, '"CXX_FOR_BUILD"', "JACK C++ fallback")

    llvm = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(encoding="utf-8")
    require(llvm, '"$SOURCE_DIR/cc.sh" --print-cc', "LLVM C seed")
    require(llvm, '"$SOURCE_DIR/cc.sh" --print-cxx', "LLVM C++ seed")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "Bootstrap compiler boundary", "compiler ledger section")
    require(ledger, "cross compiler cannot leak backward", "target bleed guard")

    print("WHP bootstrap compiler policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
