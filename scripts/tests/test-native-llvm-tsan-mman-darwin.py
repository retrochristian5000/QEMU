#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify Darwin-specific TSan signal-unsafe allocator reporting ownership."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
RTL = LLVM / "compiler-rt/lib/tsan/rtl"
SHARED = RTL / "tsan_mman.cpp"
DARWIN = RTL / "tsan_mman_darwin.cpp"
HEADER = RTL / "tsan_mman.h"
CMAKE = RTL / "CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
REGRESSION = LLVM / "compiler-rt/test/tsan/Darwin/signal-unsafe-mman.cpp"


def check_sources() -> None:
    shared = SHARED.read_text(encoding="utf-8")
    darwin = DARWIN.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    regression = REGRESSION.read_text(encoding="utf-8")

    assert shared.count("void SignalUnsafeCall(") == 1
    assert darwin.count("void SignalUnsafeCall(") == 1
    assert "#if !SANITIZER_APPLE\nvoid SignalUnsafeCall(" in shared
    assert "#if SANITIZER_APPLE" in darwin
    assert "void SignalUnsafeCall(ThreadState *thr, uptr pc);" in header
    assert shared.count("SignalUnsafeCall(thr, pc);") == 2

    # Darwin must not call into the symbolizer while the registry lock is
    # held. Non-Apple platforms keep their original reporting lock scope.
    assert (
        "  }  // Release registry lock before symbolization and report output\n"
        "  OutputReport(thr, *rep);" in darwin
    )
    assert (
        shared.index("ThreadRegistryLock l(&ctx->thread_registry);")
        < shared.index("OutputReport(thr, *rep);")
        < shared.index("rep->~ScopedReport();")
    )
    for body in (shared, darwin):
        assert "IsFiredSuppression(ctx, ReportTypeSignalUnsafe, stack)" in body
        assert "rep->AddStack(stack, true);" in body

    # Keep the existing allocator hook/fork paths in shared code.
    assert "void invoke_malloc_hook(" in shared
    assert "void invoke_free_hook(" in shared
    assert "allocator()->ForceLock();" in shared
    assert "StackDepotUnlockAfterFork(child);" in shared

    apple_cmake = cmake.split("if(APPLE)\n  list(APPEND TSAN_SOURCES", 1)[1]
    apple_cmake = apple_cmake.split("elseif(UNIX)", 1)[0]
    assert apple_cmake.count("tsan_mman_darwin.cpp") == 1
    assert cmake.count("tsan_mman_darwin.cpp") == 1

    apple_gn = gn.split('if (target_os == "mac") {', 1)[1]
    apple_gn = apple_gn.split("  } else {", 1)[0]
    assert apple_gn.count('"tsan_mman_darwin.cpp"') == 1
    assert gn.count('"tsan_mman_darwin.cpp"') == 1

    assert regression.count(
        "CHECK: WARNING: ThreadSanitizer: signal-unsafe call"
    ) == 2
    assert "CHECK: Darwin signal-unsafe allocator: OK" in regression


if __name__ == "__main__":
    check_sources()
    print("TSan Darwin memory-manager reporting split: verified")
