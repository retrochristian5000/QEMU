#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'bootstrap-native-clang.bash'

text = BOOTSTRAP.read_text(encoding='utf-8')

# Native LLVM is a host tool, so its Darwin architecture policy is independent
# from QEMU TCG's WHP_MACOS_ARCH=auto safety gate.  On Apple Silicon, auto must
# prefer arm64e when both bootstrap compilers can compile and link that ABI,
# while retaining arm64 as the compatibility fallback.
assert 'NATIVE_LLVM_MACOS_ARCH' in text
assert 'compiler_supports_macos_arch()' in text
assert 'requested_macos_arch="${NATIVE_LLVM_MACOS_ARCH:-auto}"' in text
assert 'darwin_cmake_arch=arm64e' in text
assert 'darwin_cmake_arch=arm64' in text
assert 'WHP native LLVM macOS arch:' in text

# The selected Mach-O ABI must be part of the cached toolchain identity so an
# older arm64 toolchain cannot be reused after an arm64e-capable host switches.
assert 'BOOTSTRAP_SCHEMA=9' in text
assert 'MACOS_BOOTSTRAP_ARCH=$darwin_cmake_arch' in text

# CMake's parent graph and compiler-rt ExternalProjects must consume the same
# selected architecture; otherwise clang could be arm64e while its runtimes are
# silently built for a different ABI.
assert text.count('-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch') >= 2

print('native LLVM arm64e bootstrap policy: verified')
