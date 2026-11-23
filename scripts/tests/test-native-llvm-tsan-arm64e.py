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
ASM = LIB / "tsan/rtl/tsan_interceptors_aarch64.S"
INTERCEPTORS = LIB / "tsan/rtl/tsan_interceptors_posix.cpp"
DARWIN_INTERCEPTORS = LIB / "tsan/rtl/tsan_interceptors_darwin.cpp"
DARWIN_HEADER = LIB / "tsan/rtl/tsan_interceptors_darwin.h"
TSAN_CMAKE = LIB / "tsan/rtl/CMakeLists.txt"
TSAN_GN = ROOT / (
    "toolchains/llvm-project/llvm/utils/gn/secondary/"
    "compiler-rt/lib/tsan/rtl/BUILD.gn"
)
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
SIGLONGJMP_MASK_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/"
    "siglongjmp-deferred-mask.c"
)
DARWIN_ALTSTACK_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "siglongjmp-altstack.c"
)
DARWIN_TEST = ROOT / (
    "toolchains/llvm-project/compiler-rt/test/tsan/Darwin/"
    "setjmp-tail-call.c"
)


def check_sources() -> None:
    source = ASM.read_text(encoding="utf-8")
    regression = DARWIN_TEST.read_text(encoding="utf-8")
    interceptors = INTERCEPTORS.read_text(encoding="utf-8")
    darwin_interceptors = DARWIN_INTERCEPTORS.read_text(encoding="utf-8")
    darwin_header = DARWIN_HEADER.read_text(encoding="utf-8")
    tsan_cmake = TSAN_CMAKE.read_text(encoding="utf-8")
    tsan_gn = TSAN_GN.read_text(encoding="utf-8")
    longjmp_regression = LONGJMP_TEST.read_text(encoding="utf-8")
    siglongjmp_regression = SIGLONGJMP_MASK_TEST.read_text(encoding="utf-8")
    darwin_altstack_regression = DARWIN_ALTSTACK_TEST.read_text(encoding="utf-8")
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
    # Assembly entry points have exactly one AArch64 owner, for Mach-O and
    # ELF. Keep the old ISA-neutral runtime filename out of the source list.
    assert tsan_cmake.count("tsan_interceptors_aarch64.S") == 2
    assert "tsan_rtl_aarch64.S" not in tsan_cmake
    assert tsan_gn.count("tsan_interceptors_aarch64.S") == 1
    assert "tsan_rtl_aarch64.S" not in tsan_gn
    assert "tsan_interceptors_darwin.cpp" in tsan_gn
    assert "tsan_interceptors_freebsd.cpp" in tsan_gn
    assert "tsan_interceptors_linux.cpp" in tsan_gn
    assert "tsan_interceptors_glibc.cpp" in tsan_gn
    for symbol in ("setjmp", "_setjmp", "sigsetjmp", "__sigsetjmp"):
        assert f"ASM_SYMBOL_INTERCEPTOR({symbol}):" in source
    assert source.count("  BTI_C") == 4
    assert source.count("  stp     x29, x30, [sp, -32]!") == 4
    assert source.count("  ldp     x29, x30, [sp], 32") == 4
    for symbol in ("real_setjmp", "real__setjmp", "real_sigsetjmp"):
        assert re.search(
            rf"(?m)^#if !defined\(__APPLE__\)\n"
            rf"\.comm _ZN14__interception\d+{symbol}E,8,8\n#endif$",
            source,
        ), f"Mach-O must not allocate an ELF {symbol} pointer"

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

    # LongJmp() uses REAL(pthread_sigmask) before the interceptor definition.
    # DECLARE_REAL is required for both Darwin's libc symbol and other POSIX
    # platforms' __interception::real_pthread_sigmask function pointer.
    real_sigmask = re.search(
        r"DECLARE_REAL\(int, pthread_sigmask, int how,\s*"
        r"const __sanitizer_sigset_t \*set,\s*"
        r"__sanitizer_sigset_t \*oldset\)",
        interceptors,
    )
    assert real_sigmask is not None, "missing pthread_sigmask forward declaration"
    assert real_sigmask.start() < interceptors.index("static void LongJmp(")
    assert interceptors.count("TSAN_INTERCEPTOR(int, pthread_sigmask,") == 1
    assert "TSAN_INTERCEPT(pthread_sigmask);" in interceptors

    # siglongjmp must restore TSan's temporary all-blocked mask even when
    # Darwin libc intentionally skips signal-mask restoration (savemask=0).
    assert re.search(
        r"while \(sctx->oldset\.Size\(\) > buf->oldset_stack_size\)\s*\{"
        r".*?REAL\(pthread_sigmask\)\(SIG_SETMASK, &oldset, nullptr\);"
        r".*?sctx->oldset\.PopBack\(\);",
        interceptors,
        re.DOTALL,
    ), "longjmp loses the deferred-signal mask restoration"
    assert "sigsetjmp(checkpoint, savemask)" in siglongjmp_regression
    assert "run_case(0)" in siglongjmp_regression
    assert "run_case(1)" in siglongjmp_regression
    assert "sigismember(&mask, SIGTERM)" in siglongjmp_regression
    assert "siglongjmp(checkpoint, 23)" in darwin_altstack_regression
    assert "SA_ONSTACK" in darwin_altstack_regression
    assert "current.ss_flags & SS_ONSTACK" in darwin_altstack_regression

    # Darwin's deferred signal context is smaller than Linux's, and may be
    # null. These guards prevent unsafe copies from returning in the fork.
    # Keep a single POSIX signal dispatcher, but compile the Darwin-specific
    # ABI copy helpers only for Apple platforms.
    apple_sources = tsan_cmake.split(
        "if(APPLE)\n  list(APPEND TSAN_SOURCES", 1
    )[1].split("elseif(UNIX)", 1)[0]
    assert "tsan_interceptors_darwin.cpp" in apple_sources
    assert "tsan_interceptors_darwin.h" in tsan_cmake
    assert "DarwinSignalContext ctx;" in interceptors
    assert "CopyDarwinSignalInfo(&signal->siginfo, info);" in interceptors
    assert "CopyDarwinSignalContext(&signal->ctx, ctx);" in interceptors
    assert "u64 opaque[56 / sizeof(u64)]" not in interceptors
    assert "kSignalInfoCopySize" not in interceptors
    assert "opaque[56 / sizeof(__sanitizer::u64)]" in darwin_header
    assert "sizeof(ucontext_t) == sizeof(DarwinSignalContext)" in darwin_interceptors
    assert "sizeof(siginfo_t) <= 128" in darwin_interceptors
    assert "internal_memcpy(destination, source, sizeof(siginfo_t))" in darwin_interceptors
    assert "internal_memcpy(destination, source, sizeof(ucontext_t))" in darwin_interceptors
    assert "signal->has_ctx = (ctx != nullptr)" in interceptors
    assert "signal->has_ctx ? &signal->ctx : nullptr" in interceptors
    assert "DontNeedShadowFor((uptr)sctx," in interceptors
    assert "RoundUpTo(sizeof(*sctx), GetPageSizeCached())" in interceptors
    assert "SA_SIGINFO | SA_ONSTACK" in signal_regression
    assert "pthread_kill(main_thread, SIGUSR1)" in signal_regression
    assert "sizeof(siginfo_t) <= 128" in signal_layout
    assert "sizeof(ucontext_t) == 56" in signal_layout
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
