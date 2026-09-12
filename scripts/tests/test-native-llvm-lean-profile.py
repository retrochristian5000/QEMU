#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP_PATH = ROOT / 'scripts' / 'bootstrap-native-clang.bash'
bootstrap = BOOTSTRAP_PATH.read_text(encoding='utf-8')

# Keep the bootstrap script syntactically valid before checking the policy
# strings below.  This test intentionally stays structural so it runs on Linux
# CI even though the lean runtime profile is consumed only by Darwin builds.
subprocess.run(['bash', '-n', str(BOOTSTRAP_PATH)], check=True)

# Building the compiler at -O3 spends considerably more optimizer work than the
# WHP host toolchain needs.  Keep Release/NDEBUG semantics, use -O2, and allow
# scheduling-only host tuning when the bootstrap compiler accepts it.  Do not
# raise the generated toolchain's ISA floor with -mcpu/-march native flags.
assert "llvm_bootstrap_cflags='-O2 -DNDEBUG'" in bootstrap
assert "llvm_bootstrap_cxxflags='-O2 -DNDEBUG'" in bootstrap
assert 'compiler_accepts_native_tune()' in bootstrap
assert '-mtune=native' in bootstrap
assert 'llvm_bootstrap_cflags="$llvm_bootstrap_cflags -mtune=native"' in bootstrap
assert 'llvm_bootstrap_cxxflags="$llvm_bootstrap_cxxflags -mtune=native"' in bootstrap
assert '"-DCMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags"' in bootstrap
assert '"-DCMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags"' in bootstrap
assert 'CMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags' in bootstrap
assert 'CMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags' in bootstrap

# LLVM telemetry is not part of the QEMU compiler/linker contract.
assert '-DLLVM_ENABLE_TELEMETRY=OFF' in bootstrap
assert 'LLVM_ENABLE_TELEMETRY=OFF' in bootstrap

# compiler-rt is an ExternalProject on Darwin.  Remove runtimes that WHP does
# not consume, while retaining sanitizers, libFuzzer, and the profile runtime
# used by QEMU diagnostics/fuzzing/coverage workflows.
runtime_off = (
    'COMPILER_RT_ENABLE_IOS=OFF',
    'COMPILER_RT_ENABLE_MACCATALYST=OFF',
    'COMPILER_RT_ENABLE_WATCHOS=OFF',
    'COMPILER_RT_ENABLE_TVOS=OFF',
    'COMPILER_RT_ENABLE_XROS=OFF',
    'COMPILER_RT_BUILD_XRAY=OFF',
    'COMPILER_RT_BUILD_CTX_PROFILE=OFF',
    'COMPILER_RT_BUILD_MEMPROF=OFF',
    'COMPILER_RT_BUILD_ORC=OFF',
    'COMPILER_RT_BUILD_GWP_ASAN=OFF',
    'COMPILER_RT_INCLUDE_TESTS=OFF',
)
runtime_on = (
    'COMPILER_RT_BUILD_SANITIZERS=ON',
    'COMPILER_RT_BUILD_LIBFUZZER=ON',
    'COMPILER_RT_BUILD_PROFILE=ON',
)

assert 'darwin_runtimes_cmake_args=' in bootstrap
runtime_start = bootstrap.index('darwin_runtimes_cmake_args=')
runtime_end = bootstrap.index('cmake_darwin_runtime_args=(', runtime_start)
runtime_block = bootstrap[runtime_start:runtime_end]
for policy in runtime_off + runtime_on:
    assert policy in runtime_block, policy
    assert policy in bootstrap, policy

# Do not leak compiler-rt-only variables into the separate builtins project.
assert '"-DRUNTIMES_CMAKE_ARGS=$darwin_runtimes_cmake_args"' in bootstrap
assert '"-DBUILTINS_CMAKE_ARGS=$darwin_external_cmake_args"' in bootstrap

# Any of these policy changes must invalidate an older installed compiler cache.
assert 'BOOTSTRAP_SCHEMA=8' in bootstrap
for policy in runtime_off + runtime_on:
    assert policy in bootstrap[bootstrap.index('expected_marker='):], policy

print('native LLVM lean profile tests: passed')
