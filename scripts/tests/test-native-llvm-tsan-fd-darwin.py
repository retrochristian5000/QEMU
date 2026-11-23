#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify Darwin kqueue fd interception in the pinned compiler-rt source."""

from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
RTL = LLVM / "compiler-rt/lib/tsan/rtl"
SOURCE = RTL / "tsan_fd_darwin.cpp"
SHARED = RTL / "tsan_fd.cpp"
CMAKE = RTL / "CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
REGRESSION = LLVM / "compiler-rt/test/tsan/Darwin/kqueue-fd.cpp"


def check_sources() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    shared = SHARED.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    regression = REGRESSION.read_text(encoding="utf-8")

    assert "#if SANITIZER_APPLE" in source
    assert source.count("TSAN_INTERCEPTOR(int, kqueue, void)") == 1
    assert source.count("TSAN_INTERCEPTOR(int, kevent,") == 1
    assert "SCOPED_TSAN_INTERCEPTOR(kqueue);" in source
    assert "if (fd >= 0)\n    FdPollCreate(thr, pc, fd);" in source
    assert "if (kq >= 0)\n    FdAccess(thr, pc, kq);" in source
    assert "BLOCK_REAL(kevent)(kq, changes, nchanges, events, nevents, timeout)" in source

    # Readiness events are not necessarily notifications from another thread.
    # Never invent a happens-before relationship for arbitrary kqueue filters.
    assert re.search(
        r"\\b(?:FdAcquire|FdRelease|FdPollAdd|Acquire|Release)\\s*\\(",
        source,
    ) is None

    # The shared descriptor table and Linux epoll implementation keep their
    # existing ownership; Darwin adds no second descriptor table.
    assert "struct FdContext {" in shared
    assert "void FdPollCreate(ThreadState *thr, uptr pc, int fd)" in shared
    assert "void FdClose(ThreadState *thr, uptr pc, int fd, bool write)" in shared
    assert "struct FdContext {" not in source

    apple_cmake = cmake.split("if(APPLE)\n  list(APPEND TSAN_SOURCES", 1)[1]
    apple_cmake = apple_cmake.split("elseif(UNIX)", 1)[0]
    assert apple_cmake.count("tsan_fd_darwin.cpp") == 1
    assert cmake.count("tsan_fd_darwin.cpp") == 1

    apple_gn = gn.split('if (target_os == "mac") {', 1)[1]
    apple_gn = apple_gn.split("  } else {", 1)[0]
    assert apple_gn.count('"tsan_fd_darwin.cpp"') == 1
    assert gn.count('"tsan_fd_darwin.cpp"') == 1

    assert "EVFILT_READ" in regression
    assert "EV_ADD | EV_ENABLE" in regression
    assert "CHECK: Darwin kqueue fd interception: OK" in regression


if __name__ == "__main__":
    check_sources()
    print("TSan Darwin kqueue fd ownership: verified")
