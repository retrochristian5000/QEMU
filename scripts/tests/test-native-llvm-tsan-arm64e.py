#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Assemble the pinned compiler-rt TSan tails for Darwin arm64e and ELF BTI."""

import argparse
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
LIB = ROOT / "toolchains/llvm-project/compiler-rt/lib"
ASM = LIB / "tsan/rtl/tsan_rtl_aarch64.S"
DARWIN_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "setjmp-tail-call.c"
)


def check_sources() -> None:
    source = ASM.read_text(encoding="utf-8")
    regression = DARWIN_TEST.read_text(encoding="utf-8")
    for name in ("setjmp", "_setjmp", "sigsetjmp"):
        assert f"  b       ASM_SYMBOL({name})" in source, (
            f"Darwin TSan {name} must branch via a Mach-O linker stub"
        )
    assert "@GOTPAGE" not in source, "arm64e TSan must not tail-jump via GOT"
    assert len(re.findall(r"^  br      x16$", source, re.MULTILINE)) == 4
    assert not re.search(r"^\s+br\s+x[12]$", source, re.MULTILINE)
    for name in ("check_setjmp", "check__setjmp", "check_sigsetjmp"):
        assert name in regression, f"missing Darwin TSan runtime case {name}"
    assert "%clang_tsan -O1" in regression


def assemble(clang: Path, target: str, destination: Path) -> None:
    subprocess.run(
        [str(clang), f"--target={target}", "-x", "assembler-with-cpp",
         "-I", str(LIB), "-c", str(ASM), "-o", str(destination)],
        check=True,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", type=Path, required=True)
    parser.add_argument("--objdump", type=Path, required=True)
    args = parser.parse_args()

    check_sources()
    with tempfile.TemporaryDirectory(prefix="qemu-tsan-arm64e-") as tmp:
        output = Path(tmp)
        macho = output / "tsan-arm64e.o"
        elf = output / "tsan-elf.o"
        assemble(args.clang, "arm64e-apple-macos13.0", macho)
        assemble(args.clang, "aarch64-unknown-linux-gnu", elf)

        result = subprocess.run(
            [str(args.objdump), "--macho", "--reloc", str(macho)],
            check=True, capture_output=True, text=True,
        ).stdout
        for symbol in ("_setjmp", "__setjmp", "_sigsetjmp"):
            assert any(
                re.search(r"\bBR26\b.*\b" + re.escape(symbol) + r"\b", line)
                for line in result.splitlines()
            ), f"missing Mach-O branch relocation for {symbol}"

    print("TSan arm64e stub relocations and AArch64 BTI tails: verified")


if __name__ == "__main__":
    main()
