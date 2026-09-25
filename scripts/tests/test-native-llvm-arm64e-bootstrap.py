#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'bootstrap-native-clang.bash'

text = BOOTSTRAP.read_text(encoding='utf-8')

# Native LLVM is a host tool, so its Darwin architecture policy is independent
# from QEMU TCG's WHP_MACOS_ARCH=auto safety gate.  On Apple Silicon, auto may
# select arm64e only when both bootstrap compilers can compile, link, and run
# that ABI; older macOS releases must retain arm64 as the compatibility path.
assert 'NATIVE_LLVM_MACOS_ARCH' in text
assert 'compiler_supports_macos_arch()' in text
assert 'requested_macos_arch="${NATIVE_LLVM_MACOS_ARCH:-auto}"' in text
assert 'darwin_cmake_arch=arm64e' in text
assert 'darwin_cmake_arch=arm64' in text
assert 'WHP native LLVM macOS arch:' in text
assert '"$output" >/dev/null 2>&1' in text

# The selected Mach-O ABI must be part of the cached toolchain identity so an
# older arm64 toolchain cannot be reused after an arm64e-capable host switches.
assert 'MACOS_BOOTSTRAP_ARCH=$darwin_cmake_arch' in text

# CMake's parent graph and compiler-rt ExternalProjects must consume the same
# selected architecture; otherwise clang could be arm64e while its runtimes are
# silently built for a different ABI.
assert text.count('-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch') >= 2

# Apple SME builtins must use Clang's canonical AArch64 architecture spelling.
# The old armv8a+sme form makes the arm64e compiler-rt build fail before QEMU.
compiler_rt_builtins = (
    ROOT / 'toolchains' / 'llvm-project' / 'compiler-rt' / 'lib' / 'builtins'
    / 'CMakeLists.txt'
)
if compiler_rt_builtins.is_file():
    compiler_rt_text = compiler_rt_builtins.read_text(encoding='utf-8')
    assert '-march=armv8-a+sme' in compiler_rt_text
    assert '-march=armv8a+sme' not in compiler_rt_text

# The installed compiler must be smoke-tested with the ABI selected for the
# toolchain itself.  A plain clang invocation defaults back to arm64 on macOS
# and would therefore fail to prove that an arm64e bootstrap can compile C.
assert 'smoke_arch_args=(' in text
assert '-arch "$darwin_cmake_arch"' in text
assert '"${smoke_arch_args[@]}"' in text
assert '#ifndef __arm64e__' in text
assert 'whp_arm64e_fp' in text

# The WHP Mach-O LLD fork does not yet implement ARM64_RELOC_AUTHENTICATED_POINTER.
# A trivial arm64e link probe can therefore succeed even though real LLVM objects
# later fail with "INVALID relocation has invalid width".  Never reuse the old
# ld64.lld for an arm64e bootstrap; keep Apple ld as that build's linker until
# the backend gains a real authenticated-relocation capability probe.
assert '"$darwin_cmake_arch" != arm64e' in text
assert text.index('"$darwin_cmake_arch" != arm64e') < text.index('-fuse-ld=lld')

print('native LLVM arm64e bootstrap policy: verified')
