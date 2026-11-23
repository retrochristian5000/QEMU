#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify TSan interface sources and all their build references."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
TSAN = LLVM / "compiler-rt/lib/tsan"
INTERFACE = TSAN / "interface"
RTL = TSAN / "rtl"
CMAKE = RTL / "CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
GO_SH = TSAN / "go/buildgo.sh"
GO_BAT = TSAN / "go/build.bat"
TESTS_CMAKE = TSAN / "tests/CMakeLists.txt"
PUBLIC = LLVM / "compiler-rt/include/sanitizer"

FILES = (
    "tsan_interface.cpp",
    "tsan_interface_ann.cpp",
    "tsan_interface_atomic.cpp",
    "tsan_interface_java.cpp",
    "tsan_interface.h",
    "tsan_interface_ann.h",
    "tsan_interface_java.h",
    "tsan_interface.inc",
)
RTL_INCLUDES = {
    "tsan_adaptive_delay.cpp": ("tsan_interface.h",),
    "tsan_debugging.cpp": ("tsan_interface.h",),
    "tsan_flags.cpp": ("tsan_interface.h",),
    "tsan_interceptors_mac.cpp": ("tsan_interface.h", "tsan_interface_ann.h"),
    "tsan_interceptors_memintrinsics.cpp": ("tsan_interface.h",),
    "tsan_interceptors_posix.cpp": ("tsan_interface.h",),
    "tsan_mman.cpp": ("tsan_interface.h",),
    "tsan_preinit.cpp": ("tsan_interface.h",),
    "tsan_rtl.cpp": ("tsan_interface.h",),
    "tsan_rtl_access.cpp": ("tsan_interface.inc",),
}
PRIVATE_DEPS = {
    "tsan_interface.cpp": ("tsan_rtl.h",),
    "tsan_interface_ann.cpp": (
        "tsan_adaptive_delay.h", "tsan_flags.h", "tsan_mman.h",
        "tsan_platform.h", "tsan_report.h", "tsan_rtl.h",
    ),
    "tsan_interface_atomic.cpp": (
        "tsan_adaptive_delay.h", "tsan_flags.h", "tsan_rtl.h",
    ),
    "tsan_interface_java.cpp": ("tsan_rtl.h",),
    "tsan_interface.inc": ("tsan_rtl.h",),
}


def check_sources() -> None:
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    posix_go = GO_SH.read_text(encoding="utf-8")
    windows_go = GO_BAT.read_text(encoding="utf-8")
    unit_cmake = TESTS_CMAKE.read_text(encoding="utf-8")

    for filename in FILES:
        assert (INTERFACE / filename).is_file(), filename
        assert not (RTL / filename).exists(), filename
        assert cmake.count(f"../interface/{filename}") == 1, filename
        assert gn.count(f'"../interface/{filename}"') == 1, filename

    for filename, includes in RTL_INCLUDES.items():
        source = (RTL / filename).read_text(encoding="utf-8")
        for include in includes:
            assert f'"../interface/{include}"' in source, filename

    for filename, includes in PRIVATE_DEPS.items():
        source = (INTERFACE / filename).read_text(encoding="utf-8")
        for include in includes:
            assert f'#include "../rtl/{include}"' in source, filename
            assert f'#include "{include}"' not in source, filename

    # Public API symbols stay in the existing TSan binary.
    assert "void __tsan_init()" in (INTERFACE / "tsan_interface.cpp").read_text()
    assert "void __tsan_acquire(" in (INTERFACE / "tsan_interface.cpp").read_text()
    assert "__tsan_atomic8_load(" in (INTERFACE / "tsan_interface_atomic.cpp").read_text()
    assert "__tsan_java_init(" in (INTERFACE / "tsan_interface_java.cpp").read_text()
    assert "void __tsan_read1(" in (INTERFACE / "tsan_interface.inc").read_text()
    assert (PUBLIC / "tsan_interface.h").is_file()
    assert (PUBLIC / "tsan_interface_atomic.h").is_file()

    assert "../interface/tsan_interface_atomic.cpp" in posix_go
    assert " -I../interface " in posix_go
    assert r"..\interface\tsan_interface_atomic.cpp" in windows_go
    assert r"-I..\interface" in windows_go
    assert r"..\rtl\tsan_thread.cpp" in windows_go
    assert "tsan_rtl_thread.cpp" not in windows_go
    assert "include_directories(../rtl ../interface)" in unit_cmake
    assert "lib/tsan/interface" in unit_cmake


if __name__ == "__main__":
    check_sources()
    print("TSan interface layout and build paths: verified")
