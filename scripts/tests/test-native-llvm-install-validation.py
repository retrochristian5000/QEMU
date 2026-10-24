#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise WHP's actual native LLVM usability function without a macOS SDK.

Tests a false-negative: Clang's macOS UBSan/Cocoa checks must not force
ld64.lld when the system Apple linker remains supported.
This is a hermetic policy test, not an LLVM or Mach-O runtime build.
"""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
bootstrap = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(
    encoding="utf-8"
)
start = bootstrap.index("\nusable()\n{") + 1
end = bootstrap.index("\n}\n\nverify_asan_when_requested()", start) + 3
usable = bootstrap[start:end]

# Keep the real LLVM function under test. Stub only architecture helpers,
# unrelated Windows cross-link validation, and the compiler executables.
driver = r"""#!/bin/sh
set -eu
printf '%s\n' "$*" >> "$WHP_PROBE_LOG"
for arg in "$@"; do
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
if [ "$1" = --print-targets ]; then
    printf '  aarch64    - AArch64\n  x86        - X86\n  ppc32      - PowerPC\n'
fi
exit 0
"""

probe = (
    "set -euo pipefail\n"
    "host_os=macos\n"
    'darwin_cmake_arch="$WHP_TEST_ARCH"\n'
    "sdkroot=/mock/MacOSX.sdk\n"
    "deployment_target=15.0\n"
    "llvm_default_target_triple=aarch64-apple-macosx15.0\n"
    "LLVM_WINDOWS_MANIFEST=0\n"
    "NATIVE_LLVM_ENABLE_LLDB=0\n"
    "NATIVE_LLVM_SHARED_TOOLCHAIN=0\n"
    "shared_host_libraries_usable() { return 0; }\n"
    "windows_cross_target_usable() { return 0; }\n"
    "native_target_matches_host() { return 0; }\n"
    "query_target_triple() { echo aarch64-apple-macosx15.0; }\n"
    'canonical_native_target_triple() { printf "%s\\n" "$1"; }\n'
    + usable + '\nusable "$1"\n'
)

required = (
    "ld.lld", "lld-link", "llvm-ar", "llvm-ranlib", "llvm-lib",
    "llvm-dlltool", "llvm-rc", "llvm-windres", "llvm-nm", "llvm-objcopy",
    "llvm-objdump", "llvm-strip", "llvm-readobj", "llvm-readelf",
    "llvm-config", "llvm-tblgen", "llvm-otool", "llvm-lipo", "ld64.lld",
)

with tempfile.TemporaryDirectory(prefix="whp-native-llvm-usable-") as scratch:
    base = Path(scratch)
    prefix = base / "toolchain"
    bin_dir = prefix / "bin"
    (prefix / "lib").mkdir(parents=True)
    bin_dir.mkdir()
    (prefix / "lib/libLTO.dylib").write_bytes(b"test fixture")
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
    trace = base / "clang-invocations.log"

    def run_probe(arch, fail_ubsan=False):
        trace.write_text("", encoding="utf-8")
        env = os.environ.copy()
        env.update({
            "WHP_PROBE_LOG": str(trace),
            "WHP_TEST_ARCH": arch,
            "WHP_FAIL_UBSAN": "1" if fail_ubsan else "0",
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
        assert "-framework Cocoa" in calls, (arch, calls)
        assert f"-arch {arch}" in calls, (arch, calls)

    # A failed sanitizer link still fails closed: only the unrelated
    # requirement that it use LLVM's Mach-O linker is removed.
    result, _ = run_probe("arm64", fail_ubsan=True)
    assert result.returncode != 0
    assert "native LLVM UBSan link failed" in result.stderr, result.stderr

    # A missing installed tool remains a fatal incomplete distribution.
    (bin_dir / "llvm-ar").unlink()
    result, _ = run_probe("arm64")
    assert result.returncode != 0
    assert "missing required tool: llvm-ar" in result.stderr, result.stderr

print("native LLVM macOS usability linker isolation: passed")
