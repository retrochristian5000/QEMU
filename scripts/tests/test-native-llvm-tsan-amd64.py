#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check the pinned AMD64 TSan setjmp interceptors on ELF and Darwin."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
LIB = LLVM / "compiler-rt/lib"
SOURCE = LIB / "tsan/rtl/tsan_interceptors_amd64.S"
CMAKE = LIB / "tsan/rtl/CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
DARWIN_TEST = LLVM / "compiler-rt/test/tsan/Darwin/setjmp-amd64.c"


def check_sources() -> None:
    asm = SOURCE.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    test = DARWIN_TEST.read_text(encoding="utf-8")

    assert "tsan_rtl_amd64.S" not in cmake
    assert "tsan_rtl_amd64.S" not in gn
    assert cmake.count("tsan_interceptors_amd64.S") == 2
    assert gn.count("tsan_interceptors_amd64.S") == 1
    assert asm.count("  CFI_STARTPROC") == 4
    assert asm.count("  CFI_ENDPROC") == 4
    assert asm.count("  _CET_ENDBR") == 4

    # Mach-O must not define ELF interception function-pointer storage.
    for name in ("real__setjmp", "real_sigsetjmp"):
        assert re.search(
            rf"(?m)^#if !defined\(__APPLE__\)\n"
            rf"\.comm _ZN14__interception\d+{name}E,8,8\n#endif$",
            asm,
        ), f"Darwin still declares the ELF {name} pointer"

    for name in ("setjmp", "_setjmp", "sigsetjmp"):
        assert f"jmp ASM_SYMBOL({name})" in asm
    assert ".comm _ZN14__interception16real___sigsetjmpE,8,8" in asm
    assert "ASM_SYMBOL_INTERCEPTOR(__setjmp14):" in asm
    assert "ASM_SYMBOL_INTERCEPTOR(__sigsetjmp14):" in asm
    assert "lea 8(%rsp), %rdi" in asm
    assert "lea 16(%rsp), %rdi" in asm
    assert "lea 24(%rsp), %rdi" in asm
    assert "lea 32(%rsp), %rdi" in asm

    # The lit test exercises the actual Darwin x86-64 runtime entry points.
    assert "REQUIRES: x86_64-target-arch" in test
    assert "TestSetJmp" in test
    assert "TestUnderscoreSetJmp" in test
    assert "TestSigSetJmp" in test


def assemble(clang: Path, target: str, destination: Path) -> None:
    subprocess.run(
        [
            str(clang),
            f"--target={target}",
            "-x",
            "assembler-with-cpp",
            "-I",
            str(LIB),
            "-c",
            str(SOURCE),
            "-o",
            str(destination),
        ],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--clang",
        type=Path,
        help="also cross-assemble all supported AMD64 OS object variants",
    )
    args = parser.parse_args()
    check_sources()

    if args.clang is not None:
        targets = (
            "x86_64-apple-macosx10.15",
            "x86_64-unknown-linux-gnu",
            "x86_64-unknown-freebsd",
            "x86_64-unknown-netbsd",
        )
        with tempfile.TemporaryDirectory(prefix="tsan-amd64-") as tmp:
            for index, target in enumerate(targets):
                assemble(args.clang, target, Path(tmp) / f"tsan-amd64-{index}.o")

    print("TSan AMD64 interceptor ownership and source ABI: verified")


if __name__ == "__main__":
    main()
