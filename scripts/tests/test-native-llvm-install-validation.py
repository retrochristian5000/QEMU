#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise WHP's actual native LLVM usability function without a macOS SDK.

Tests a false-negative: Clang's macOS UBSan/Cocoa checks must not force
ld64.lld when the system Apple linker remains supported.
This is a hermetic policy test, not an LLVM or Mach-O runtime build.
"""

from pathlib import Path
import os
import struct
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
bootstrap = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(
    encoding="utf-8"
)
start = bootstrap.index("\nnative_llvm_validation_error()\n{") + 1
end = bootstrap.index("\n}\n\nverify_asan_when_requested()", start) + 3
usable = bootstrap[start:end]


def bootstrap_function(name):
    start = bootstrap.index(f"\n{name}()\n{{") + 1
    end = bootstrap.index("\n}\n", start) + 3
    return bootstrap[start:end]


# Use the real installed-compiler checks. A Darwin seed is admitted
# earlier, but an installed native LLVM Clang must report its versioned
# macOS product target; arm64e must not silently inherit aarch64.
target_helpers = (ROOT / "scripts/whp-build/macos-target-abi.bash").read_text() + "\n"
target_helpers += "\n".join(bootstrap_function(name) for name in (
    "canonical_native_arch", "canonical_native_target_triple",
    "native_target_matches_host", "native_installed_target_matches_host",
    "native_target_abi_key",
))

# Keep the real LLVM function under test. Stub only architecture helpers,
# unrelated Windows cross-link validation, and the compiler executables.
driver = r"""#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$WHP_PROBE_LOG"
for arg in "$@"; do
    # Consume source on stdin like a real compiler. Otherwise the mock can
    # exit before the producing printf writes, tripping Bash pipefail.
    if [ "$arg" = "-" ]; then
        cat >/dev/null
    fi
    if [ "$arg" = "-fuse-ld=lld" ]; then
        printf 'simulated unsupported Mach-O LLD\n' >&2
        exit 83
    fi
    if [ "$arg" = "-fsanitize=undefined" ] &&
       [ "$WHP_FAIL_UBSAN" = 1 ]; then
        printf 'simulated missing compiler-rt runtime\n' >&2
        exit 84
    fi
done
if [ "$1" = -print-resource-dir ]; then
    printf '%s\n' "$WHP_TEST_RESOURCE_DIR"
fi
if [ "$1" = --print-targets ]; then
    printf '  aarch64    - AArch64\n  x86        - X86\n'
    if [ "$WHP_TEST_MISSING_BACKEND" != 1 ]; then
        printf '  ppc32      - PowerPC\n'
    fi
fi
exit 0
"""

probe = (
    "set -euo pipefail\n"
    "host_os=macos\n"
    "host_tag=aarch64\n"
    "host_id=aarch64-apple-darwin\n"
    'darwin_cmake_arch="$WHP_TEST_ARCH"\n'
    "sdkroot=/mock/MacOSX.sdk\n"
    'deployment_target="$WHP_TEST_DEPLOYMENT"\n'
    'case "$darwin_cmake_arch" in\n'
    '  arm64e) llvm_default_target_triple="arm64e-apple-macosx$deployment_target" ;;\n'
    '  *) llvm_default_target_triple="aarch64-apple-macosx$deployment_target" ;;\n'
    'esac\n'
    "LLVM_WINDOWS_MANIFEST=0\n"
    "NATIVE_LLVM_ENABLE_LLDB=0\n"
    "NATIVE_LLVM_SHARED_TOOLCHAIN=0\n"
    'SOURCE_DIR="$WHP_TEST_SOURCE_DIR"\n'
    "shared_host_libraries_usable() { return 0; }\n"
    "windows_cross_target_usable() { return 0; }\n"
    + target_helpers + '\n'
    'query_target_triple() { case "$1" in */clang++) printf "%s\\n" '
        '"$WHP_TEST_CXX_TARGET" ;; *) printf "%s\\n" '
        '"$WHP_TEST_TARGET" ;; esac; }\n'
    + usable + '\nusable "$1"\n'
)

required = (
    "ld.lld", "lld-link", "llvm-ar", "llvm-ranlib", "llvm-lib",
    "llvm-dlltool", "llvm-rc", "llvm-windres", "llvm-nm", "llvm-objcopy",
    "llvm-objdump", "llvm-strip", "llvm-readobj", "llvm-readelf",
    "llvm-config", "llvm-tblgen", "llvm-otool", "llvm-lipo",
    "llvm-libtool-darwin", "ld64.lld",
)

# The distribution target must install every Darwin archive tool consumed
# by the nested LLVM builtins/runtimes graphs; building it is not enough.
assert "llvm-otool;llvm-lipo;llvm-libtool-darwin;LTO;builtins;runtimes" in bootstrap

with tempfile.TemporaryDirectory(prefix="whp-native-llvm-usable-") as scratch:
    base = Path(scratch)
    prefix = base / "toolchain"
    bin_dir = prefix / "bin"
    (prefix / "lib").mkdir(parents=True)
    bin_dir.mkdir()
    (prefix / "lib/libLTO.dylib").write_bytes(b"test fixture")
    # The sanitizer dylib must belong to this Clang resource directory.
    resource = prefix / "lib/clang/whp-test"
    darwin_runtime = resource / "lib/darwin"
    darwin_runtime.mkdir(parents=True)
    # Model an installed Clang distribution, not just a compiler driver.
    # Native LLVM usability now checks these generated resource headers.
    resource_headers = resource / "include"
    resource_headers.mkdir()
    for header in ("arm_neon.h", "arm_bf16.h", "arm_vector_types.h"):
        (resource_headers / header).write_text(
            "/* fixture generated resource header */\n", encoding="utf-8"
        )
    # The real ABI auditor inspects inner archive objects, not just the FAT
    # label. Give the isolated usability test both native Mach-O ABI slices.
    def native_archive(subtype: int) -> bytes:
        obj = struct.pack("<8I", 0xFEEDFACF, 0x0100000C,
                          subtype, 1, 0, 0, 0, 0)
        fields = (
            f"{'abi.o/':<16}{0:<12}{0:<6}{0:<6}{0:<8}{len(obj):<10}"
        ).encode("ascii")
        header = fields + bytes((96, 10))
        assert len(header) == 60
        return b"!<arch>\n" + header + obj

    plain_archive = native_archive(0)
    signed_archive = native_archive(0x80000002)
    first_offset = 8 + 2 * 20
    second_offset = first_offset + len(plain_archive)
    fat_table = (
        struct.pack(">II", 0xCAFEBABE, 2)
        + struct.pack(">IIIII", 0x0100000C, 0, first_offset,
                      len(plain_archive), 2)
        + struct.pack(">IIIII", 0x0100000C, 0x80000002, second_offset,
                      len(signed_archive), 2)
    )
    builtins_archive = darwin_runtime / "libclang_rt.osx.a"
    valid_builtins = fat_table + plain_archive + signed_archive
    builtins_archive.write_bytes(valid_builtins)

    ubsan_dylib = darwin_runtime / "libclang_rt.ubsan_osx_dynamic.dylib"
    ubsan_dylib.write_bytes(b"mock Mach-O UBSan runtime")
    clang = bin_dir / "clang"
    clang.write_text(driver, encoding="utf-8")
    clang.chmod(0o755)
    (bin_dir / "clang++").symlink_to("clang")
    # macOS runners need not provide /bin/true (the normal location is
    # /usr/bin/true). Keep every fixture executable and symlink *inside*
    # this temporary prefix: a dangling symlink was being misdiagnosed as
    # a missing ld.lld before the real native LLVM build even started.
    fixture_tool = bin_dir / "whp-fixture-tool"
    fixture_tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    fixture_tool.chmod(0o755)
    for name in required:
        (bin_dir / name).symlink_to("whp-fixture-tool")
    # Mimic llvm-lipo's architecture list without a macOS host. An arm64
    # dylib alone must never satisfy an explicit arm64e ABI request.
    (bin_dir / "llvm-lipo").unlink()
    lipo = bin_dir / "llvm-lipo"
    lipo.write_text(
        '#!/bin/sh\n'
        'test "$1" = "-archs" || exit 1\n'
        'printf "%s\\n" "$WHP_TEST_RUNTIME_ARCHS"\n',
        encoding="utf-8",
    )
    lipo.chmod(0o755)
    # Fail with the actual fixture defect before extracting usable(). A
    # dangling symlink would otherwise be attributed to missing native LLVM.
    assert fixture_tool.is_file() and os.access(fixture_tool, os.X_OK)
    assert all(os.access(bin_dir / name, os.X_OK) for name in required)
    trace = base / "clang-invocations.log"

    def run_probe(arch, fail_ubsan=False, missing_backend=False,
                  target=None, cxx_target=None,
                  deployment="15.0", runtime_archs="arm64 arm64e"):
        if target is None:
            target_arch = 'arm64e' if arch == 'arm64e' else 'aarch64'
            target = f'{target_arch}-apple-macosx{deployment}'
        trace.write_text("", encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "WHP_PROBE_LOG": str(trace),
            "WHP_TEST_SOURCE_DIR": str(ROOT),
            "WHP_TEST_RESOURCE_DIR": str(resource),
            "WHP_TEST_RUNTIME_ARCHS": runtime_archs,
            "WHP_TEST_ARCH": arch,
            "WHP_FAIL_UBSAN": "1" if fail_ubsan else "0",
            "WHP_TEST_MISSING_BACKEND": "1" if missing_backend else "0",
            "WHP_TEST_TARGET": target,
            "WHP_TEST_CXX_TARGET": cxx_target if cxx_target is not None else target,
            "WHP_TEST_DEPLOYMENT": deployment,
        })
        p = subprocess.run(
            ["bash", "-c", probe, "--", str(prefix)],
            env=env, capture_output=True, text=True, check=False,
        )
        return p, trace.read_text(encoding="utf-8")

    for arch in ("arm64", "arm64e"):
        result, calls = run_probe(arch)
        assert result.returncode == 0, (arch, result.stderr)
        assert "-fuse-ld=lld" not in calls, (arch, calls)
        assert "-fsanitize=undefined" in calls, (arch, calls)
        assert "-print-resource-dir" in calls, (arch, calls)
        assert "-framework Cocoa" in calls, (arch, calls)
        assert f"-arch {arch}" in calls, (arch, calls)

    # Do not stub out the archive auditor. Missing builtins and a FAT
    # descriptor lying about an ARM64e slice must both fail the real check.
    builtins_archive.unlink()
    result, _ = run_probe("arm64e")
    assert result.returncode != 0 and "[ABI]" in result.stderr, result.stderr
    assert "no installed libclang_rt*.a archives" in result.stderr, result.stderr

    # Differentiate no static runtimes at all from an incomplete install that
    # has optional runtimes but lacks the mandatory host builtins archive.
    optional_archive = darwin_runtime / "libclang_rt.profile_osx.a"
    optional_archive.write_bytes(plain_archive)
    result, _ = run_probe("arm64e")
    assert result.returncode != 0 and "[ABI]" in result.stderr, result.stderr
    assert "missing compiler-rt builtins archive" in result.stderr, result.stderr
    optional_archive.unlink()

    builtins_archive.write_bytes(fat_table + plain_archive + plain_archive)
    result, _ = run_probe("arm64e")
    assert result.returncode != 0 and "[ABI]" in result.stderr, result.stderr
    assert "disagrees with FAT table" in result.stderr, result.stderr
    builtins_archive.write_bytes(valid_builtins)

    # Missing Clang resource headers must still reject an incomplete install.
    neon_header = resource_headers / "arm_neon.h"
    neon_header.unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0, result.stderr
    assert "[resource]" in result.stderr and "arm_neon.h" in result.stderr
    neon_header.write_text(
        "/* fixture generated resource header */\n", encoding="utf-8"
    )

    # Version punctuation and recognized CPU aliases remain compatible,
    # but the installed compiler must not regress to its Darwin seed triple.
    for c_target, cxx_target in (
        ("aarch64-apple-macosx15.0.0", "aarch64-apple-macosx15"),
        ("arm64-apple-macosx15.0", "aarch64-apple-macosx15.0"),
        ("aarch64-apple-macos15.0", "arm64-apple-macosx15"),
    ):
        result, _ = run_probe("arm64", target=c_target, cxx_target=cxx_target)
        assert result.returncode == 0, (c_target, cxx_target, result.stderr)

    # ARM64e default targets must carry the PAC ABI even when the host CPU
    # runs AArch64 code and an explicit -arch arm64e probe would succeed.
    result, _ = run_probe("arm64e", target="aarch64-apple-macosx15.0")
    assert result.returncode != 0 and "[ABI]" in result.stderr, result.stderr
    result, _ = run_probe("arm64e", target="arm64e-apple-darwin24.0.0")
    assert result.returncode != 0 and "[ABI]" in result.stderr, result.stderr

    for c_target, cxx_target in (
        ("aarch64-apple-darwin24.0.0", "aarch64-apple-macosx15.0"),
        ("aarch64-apple-macosx15.0", "arm64-apple-darwin24.0.0"),
        ("aarch64-apple-darwin27.2.0", "arm64-apple-macosx27.2"),
    ):
        result, _ = run_probe(
            "arm64", target=c_target, cxx_target=cxx_target,
            deployment="27.2" if "27.2" in c_target else "15.0",
        )
        assert result.returncode != 0 and "[ABI]" in result.stderr, (
            c_target, cxx_target, result.stderr
        )

    # Real version drift must still fail, even if one compiler matches.
    for c_target, cxx_target in (
        ("aarch64-apple-darwin24.1.0", "aarch64-apple-macosx15.0"),
        ("aarch64-apple-macosx15.0", "aarch64-apple-macosx15.0.1"),
        ("aarch64-apple-macosx15.0", "aarch64-apple-ios15.0"),
    ):
        result, _ = run_probe("arm64", target=c_target, cxx_target=cxx_target)
        assert result.returncode != 0, (c_target, cxx_target)
        assert "[ABI]" in result.stderr, result.stderr

    # Clang accepting the flag does not prove compiler-rt was installed.
    # Catch a missing dylib before a confusing linker error occurs.
    ubsan_dylib.unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0, result.stderr
    assert "[runtime]" in result.stderr and "missing installed compiler-rt UBSan dylib" in result.stderr
    ubsan_dylib.write_bytes(b"mock Mach-O UBSan runtime")

    # An ordinary arm64 compiler-rt dylib cannot satisfy arm64e PAC ABI.
    result, calls = run_probe("arm64e", runtime_archs="arm64")
    assert result.returncode != 0, result.stderr
    assert "[ABI]" in result.stderr
    assert "lacks arm64e slice" in result.stderr
    assert "-fsanitize=undefined" not in calls, calls

    # A failed sanitizer link still fails closed: only the unrelated
    # requirement that it use LLVM's Mach-O linker is removed.
    result, _ = run_probe("arm64", fail_ubsan=True)
    assert result.returncode != 0
    assert "[runtime]" in result.stderr, result.stderr
    assert "native LLVM UBSan link failed" in result.stderr, result.stderr
    assert "simulated missing compiler-rt runtime" in result.stderr, result.stderr

    # Darwin linker payloads also get an explicit category and filename.
    (prefix / "lib/libLTO.dylib").rename(prefix / "lib/libLTO.missing")
    result, _ = run_probe("arm64")
    assert result.returncode != 0
    assert "[runtime]" in result.stderr, result.stderr
    assert "libLTO.dylib" in result.stderr, result.stderr
    (prefix / "lib/libLTO.missing").rename(prefix / "lib/libLTO.dylib")

    (bin_dir / "llvm-lipo").unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0
    assert "[tool]" in result.stderr, result.stderr
    assert "missing required tool: llvm-lipo" in result.stderr, result.stderr
    # Restore the slice-reporting mock, not the success-only stub; otherwise
    # later ABI mismatch tests are intercepted by an empty lipo result.
    lipo.write_text(
        '#!/bin/sh\n'
        'test "$1" = "-archs" || exit 1\n'
        'printf "%s\\n" "$WHP_TEST_RUNTIME_ARCHS"\n',
        encoding="utf-8",
    )
    lipo.chmod(0o755)

    # A previously built llvm-libtool-darwin that was omitted from the
    # installed distribution must invalidate an otherwise usable cache.
    (bin_dir / "llvm-libtool-darwin").unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0
    assert "[tool]" in result.stderr, result.stderr
    assert "missing required tool: llvm-libtool-darwin" in result.stderr, result.stderr
    (bin_dir / "llvm-libtool-darwin").symlink_to("whp-fixture-tool")

    # A missing backend is an ABI-capability failure, not a missing executable.
    result, _ = run_probe("arm64", missing_backend=True)
    assert result.returncode != 0
    assert "[ABI]" in result.stderr, result.stderr
    assert "ppc32" in result.stderr, result.stderr

    # Report both sides of a target mismatch so a rebuilt Clang can be audited.
    result, _ = run_probe("arm64", target="x86_64-apple-macosx15.0")
    assert result.returncode != 0
    assert "[ABI]" in result.stderr, result.stderr
    assert "x86_64-apple-macosx15.0" in result.stderr, result.stderr
    assert "aarch64-apple-macosx15.0" in result.stderr, result.stderr

    # A missing installed tool remains a fatal incomplete distribution.
    (bin_dir / "llvm-ar").unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0
    assert "[tool]" in result.stderr, result.stderr
    assert "missing required tool: llvm-ar" in result.stderr, result.stderr

print("native LLVM macOS usability linker isolation: passed")
