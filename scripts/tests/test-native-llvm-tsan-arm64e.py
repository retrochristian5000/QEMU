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
INTERCEPTORS = LIB / "tsan/rtl/tsan_interceptors_posix.cpp"
SIGNAL_CONTEXT_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "signal-async-context.c"
)
SIGNAL_LAYOUT_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "signal-context-layout.c"
)
SHADOW_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/"
    "signal_sigctx_clear_shadow.cpp"
)
LONGJMP_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "longjmp-shadow-stack.c"
)
DARWIN_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "setjmp-tail-call.c"
)


def check_sources() -> None:
    source = ASM.read_text(encoding="utf-8")
    regression = DARWIN_TEST.read_text(encoding="utf-8")
    interceptors = INTERCEPTORS.read_text(encoding="utf-8")
    longjmp_regression = LONGJMP_TEST.read_text(encoding="utf-8")
    signal_regression = SIGNAL_CONTEXT_TEST.read_text(encoding="utf-8")
    signal_layout = SIGNAL_LAYOUT_TEST.read_text(encoding="utf-8")
    shadow_regression = SHADOW_TEST.read_text(encoding="utf-8")
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

    # Darwin's _longjmp must unwind the shadow stack just like longjmp.
    assert re.search(
        r"#if SANITIZER_APPLE \|\| SANITIZER_NETBSD\s+"
        r"TSAN_INTERCEPTOR\(void, _longjmp,", interceptors
    ), "missing Darwin _longjmp interceptor"
    interceptor = interceptors.split(
        "TSAN_INTERCEPTOR(void, _longjmp,", 1
    )[1].split("#endif", 1)[0]
    assert "LongJmp(cur_thread(), env);" in interceptor
    assert re.search(
        r"#if SANITIZER_APPLE \|\| SANITIZER_NETBSD\s+"
        r"TSAN_INTERCEPT\(_longjmp\);", interceptors
    ), "missing Darwin _longjmp registration"
    assert "_setjmp(env)" in longjmp_regression
    assert "_longjmp(*env, 37)" in longjmp_regression
    assert "10000000" in longjmp_regression
    assert "%clang_tsan -O1" in longjmp_regression

    # Darwin's deferred signal context is smaller than Linux's, and may be
    # null. These guards prevent unsafe copies from returning in the fork.
    assert "u64 opaque[56 / sizeof(u64)]" in interceptors
    assert "kSignalInfoCopySize = SANITIZER_WORDSIZE == 64 ? 104 : 64" in interceptors
    assert "internal_memcpy(&signal->siginfo, info, kSignalInfoCopySize)" in interceptors
    assert "signal->has_ctx = (ctx != nullptr)" in interceptors
    assert "signal->has_ctx ? &signal->ctx : nullptr" in interceptors
    assert "DontNeedShadowFor((uptr)sctx," in interceptors
    assert "RoundUpTo(sizeof(*sctx), GetPageSizeCached())" in interceptors
    assert "SA_SIGINFO | SA_ONSTACK" in signal_regression
    assert "pthread_kill(main_thread, SIGUSR1)" in signal_regression
    assert "sizeof(siginfo_t) == 104" in signal_layout
    assert "uc_mcontext) == 56" in signal_layout
    assert "CHECK-NOT: WARNING: ThreadSanitizer: data race" in shadow_regression


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
