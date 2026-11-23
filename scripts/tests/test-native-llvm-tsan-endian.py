#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify endian-safe TSan MD5 word decoding and cross-platform source lists."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LLVM = ROOT / "toolchains/llvm-project"
TSAN = LLVM / "compiler-rt/lib/tsan"
RTL = TSAN / "rtl"
ENDIAN = RTL / "tsan_endian.cpp"
ENDIAN_LITTLE = RTL / "tsan_endian_little.cpp"
HEADER = RTL / "tsan_endian.h"
MD5 = RTL / "tsan_md5.cpp"
SHADOW = RTL / "tsan_shadow.h"
CMAKE = RTL / "CMakeLists.txt"
GN = LLVM / "llvm/utils/gn/secondary/compiler-rt/lib/tsan/rtl/BUILD.gn"
POSIX_GO = TSAN / "go/buildgo.sh"
WINDOWS_GO = TSAN / "go/build.bat"
UNIT_CMAKE = TSAN / "tests/unit/CMakeLists.txt"
UNIT_TEST = TSAN / "tests/unit/tsan_endian_test.cpp"


def check_sources() -> None:
    endian = ENDIAN.read_text(encoding="utf-8")
    little = ENDIAN_LITTLE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    md5 = MD5.read_text(encoding="utf-8")
    shadow = SHADOW.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    posix_go = POSIX_GO.read_text(encoding="utf-8")
    windows_go = WINDOWS_GO.read_text(encoding="utf-8")
    unit_cmake = UNIT_CMAKE.read_text(encoding="utf-8")
    test = UNIT_TEST.read_text(encoding="utf-8")

    # Exactly one decoder is defined: native memcpy on little-endian
    # targets, otherwise the big-endian or portable fallback implementation.
    assert "void ReadLittleEndian32Words(u32 *dst, const void *src, uptr count);" in header
    assert endian.count("void ReadLittleEndian32Words(") == 1
    assert little.count("void ReadLittleEndian32Words(") == 1
    assert "#if !defined(__BYTE_ORDER__) || !defined(__ORDER_LITTLE_ENDIAN__) ||" in endian
    assert "__BYTE_ORDER__ != __ORDER_LITTLE_ENDIAN__" in endian
    assert "#if defined(__BYTE_ORDER__) && defined(__ORDER_LITTLE_ENDIAN__) &&" in little
    assert "__BYTE_ORDER__ == __ORDER_LITTLE_ENDIAN__" in little
    assert "internal_memcpy(dst, src, count * sizeof(*dst));" in little
    assert "__builtin_bswap32" not in little
    assert "__ORDER_BIG_ENDIAN__" in endian
    assert "internal_memcpy(dst, src, count * sizeof(*dst));" in endian
    assert "__builtin_bswap32(dst[i]);" in endian
    assert "bytes[off + 3]" in endian
    assert "ReadLittleEndian32Words(" not in shadow

    # MD5 consumes decoded words, not native-endian or aliased input.
    assert '#include "tsan_endian.h"' in md5
    assert "#define SET(n) (ctx->block[n])" in md5
    assert "ReadLittleEndian32Words(ctx->block, ptr, 16);" in md5
    assert "*(const MD5_u32plus *)&ptr[" not in md5
    assert "STEP(F, a, b, c, d, SET(0), 0xd76aa478, 7)" in md5
    assert "STEP(I, b, c, d, a, GET(9), 0xeb86d391, 21)" in md5

    # The full compiler-rt build and the Go unity builds must include both
    # MD5 and its decoder, without duplicating or leaving stale sources.
    assert cmake.count("  tsan_endian.cpp\n") == 1
    assert cmake.count("  tsan_endian_little.cpp\n") == 1
    assert cmake.count("  tsan_endian.h\n") == 1
    assert gn.count('"tsan_endian.cpp"') == 1
    assert gn.count('"tsan_endian_little.cpp"') == 1
    assert gn.count('"tsan_endian.h"') == 1
    assert posix_go.count("../rtl/tsan_endian.cpp") == 1
    assert posix_go.count("../rtl/tsan_endian_little.cpp") == 1
    assert windows_go.count(r"..\rtl\tsan_endian.cpp") == 1
    assert windows_go.count(r"..\rtl\tsan_endian_little.cpp") == 1
    assert posix_go.index("../rtl/tsan_endian.cpp") < posix_go.index("../rtl/tsan_md5.cpp")
    assert windows_go.index(r"..\rtl\tsan_endian.cpp") < windows_go.index(
        r"..\rtl\tsan_md5.cpp"
    )

    # Runtime tests exercise unaligned input and standard MD5 vectors,
    # including the full-block and padded-block update paths.
    assert "  tsan_endian_test.cpp\n" in unit_cmake
    assert "TEST(Endian, LittleEndian32WordsUnaligned)" in test
    assert "TEST(Endian, LittleEndian32WordsFullBlock)" in test
    assert "ReadLittleEndian32Words(words, input + 1, 16);" in test
    assert "TEST(Endian, MD5ReferenceVectors)" in test
    for expected in (
        "0x12345678u", "0x90abcdefu",
        "d41d8cd98f00b204e9800998ecf8427e",
        "900150983cd24fb0d6963f7d28e17f72",
        "014842d480b571495a4a0363793f7367",
        "c743a45e0d2e6a95cb859adae0248435",
    ):
        assert expected in test, expected


if __name__ == "__main__":
    check_sources()
    print("TSan endian decode, MD5 and all build paths: verified")
