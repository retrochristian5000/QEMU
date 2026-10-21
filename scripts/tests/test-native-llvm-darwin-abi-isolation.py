#!/usr/bin/env python3
"""Source-contract guard for native compiler-rt runtime architecture selection."""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
script = (root / "scripts/bootstrap-native-clang.bash").read_text(encoding="utf-8")
assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in script
assert "darwin_runtime_native_arch_only=OFF" in script
assert "darwin_runtime_native_arch_only=ON" in script
assert "-DCOMPILER_RT_DARWIN_NATIVE_ARCH_ONLY=ON" in script
assert 'darwin_runtimes_cmake_args="$darwin_external_cmake_args"' in script
assert '"-DBUILTINS_CMAKE_ARGS=$darwin_external_cmake_args"' in script
assert '"-DRUNTIMES_CMAKE_ARGS=$darwin_runtimes_cmake_args"' in script
assert "COMPILER_RT_DARWIN_NATIVE_ARCH_ONLY=$darwin_runtime_native_arch_only" in script
assert "BOOTSTRAP_SCHEMA=14" in script
assert "darwin_cmake_arch=arm64e" in script
assert "darwin_cmake_arch=arm64" in script
assert "darwin_cmake_arch=x86_64" in script
assert "--target=i686-w64-windows-gnu" in script, (
    "X86 cross-target support must remain usable independently of the macOS host ABI"
)
print("Native Darwin compiler-rt builtins/runtime ABI isolation: verified")
