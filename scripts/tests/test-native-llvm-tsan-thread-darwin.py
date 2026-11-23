#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check portable TSan thread ownership and Darwin pthread lifecycle wiring."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
RTL = LLVM / "compiler-rt/lib/tsan/rtl"
SHARED = RTL / "tsan_thread.cpp"
DARWIN = RTL / "tsan_thread_darwin.cpp"
PLATFORM = RTL / "tsan_platform_mac.cpp"
PLATFORM_HEADER = RTL / "tsan_platform.h"
CMAKE = RTL / "CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
GO = LLVM / "compiler-rt/lib/tsan/go/buildgo.sh"
REGRESSION = LLVM / "compiler-rt/test/tsan/Darwin/thread-lifecycle.cpp"


def check_sources() -> None:
    shared = SHARED.read_text(encoding="utf-8")
    darwin = DARWIN.read_text(encoding="utf-8")
    platform = PLATFORM.read_text(encoding="utf-8")
    header = PLATFORM_HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    go = GO.read_text(encoding="utf-8")
    regression = REGRESSION.read_text(encoding="utf-8")

    for old in (cmake, gn, go):
        assert "tsan_rtl_thread.cpp" not in old
    assert cmake.count("tsan_thread.cpp") == 1
    assert gn.count('"tsan_thread.cpp"') == 1
    assert go.count("../rtl/tsan_thread.cpp") == 1

    # Registry, join, leak accounting, and fibers are portable operations.
    for symbol in (
        "void ThreadFinalize(", "Tid ThreadCreate(", "void ThreadStart(",
        "void ThreadFinish(", "void ThreadJoin(", "void FiberSwitch(",
    ):
        assert symbol in shared
        assert symbol not in darwin

    assert "#if SANITIZER_APPLE" in darwin
    assert "#if !SANITIZER_GO" in darwin
    # Apple exposes PTHREAD_DESTRUCTOR_ITERATIONS through <limits.h>.
    # A file split must carry the declaration header with its static_assert.
    assert "#include <limits.h>" in darwin
    assert "static_assert(PTHREAD_DESTRUCTOR_ITERATIONS == 4" in darwin
    assert "static pthread_key_t thread_state_key;" in darwin
    for symbol in (
        "ThreadState *cur_thread()", "void set_cur_thread(",
        "void cur_thread_finalize()", "static void ThreadCreateCallback(",
        "static void ThreadTerminateCallback(",
        "void ImitateTlsWrite(", "int call_pthread_cancel_with_cleanup(",
    ):
        assert symbol in darwin
        assert symbol not in platform

    assert "void InitializeDarwinThreadSupport();" in header
    assert "InitializeDarwinThreadSupport();" in platform
    assert platform.index(
        "CheckAndProtect(true, true, true)"
    ) < platform.index(
        "InitializeDarwinThreadSupport();"
    ) < platform.index("InitializeDarwinLongJmp();")

    assert darwin.index(
        "InitializeThreadStateStorage();"
    ) < darwin.index("InstallPthreadIntrospectionHook(callbacks);")
    assert "ThreadEventCallbacks callbacks" in darwin

    apple_cmake = cmake.split("if(APPLE)\n  list(APPEND TSAN_SOURCES", 1)[1]
    apple_cmake = apple_cmake.split("elseif(UNIX)", 1)[0]
    assert apple_cmake.count("tsan_thread_darwin.cpp") == 1
    assert cmake.count("tsan_thread_darwin.cpp") == 1

    apple_gn = gn.split('if (target_os == "mac") {', 1)[1]
    apple_gn = apple_gn.split("  } else {", 1)[0]
    assert apple_gn.count('"tsan_thread_darwin.cpp"') == 1
    assert gn.count('"tsan_thread_darwin.cpp"') == 1

    assert "pthread_join(thread, nullptr)" in regression
    assert "dispatch_group_async_f(" in regression
    assert "CHECK: Darwin TSan pthread and GCD lifecycle: OK" in regression


if __name__ == "__main__":
    check_sources()
    print("TSan Darwin thread lifecycle and portable thread source: verified")
