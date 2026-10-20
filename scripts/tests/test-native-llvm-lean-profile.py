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

# Release must retain NDEBUG while avoiding the extra optimizer work of -O3.
# Keep native LLVM C/C++ compilation independent from QEMU host CPU tuning.
assert "llvm_bootstrap_cflags='-O2 -DNDEBUG'" in bootstrap
assert "llvm_bootstrap_cxxflags='-O2 -DNDEBUG'" in bootstrap
assert 'compiler_accepts_native_tune()' not in bootstrap
assert '-mtune=native' not in bootstrap
assert '-march=native' not in bootstrap
assert '-mcpu=native' not in bootstrap
assert '"-DCMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags"' in bootstrap
assert '"-DCMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags"' in bootstrap
assert 'CMAKE_C_FLAGS_RELEASE=$llvm_bootstrap_cflags' in bootstrap
assert 'CMAKE_CXX_FLAGS_RELEASE=$llvm_bootstrap_cxxflags' in bootstrap

# CPPFLAGS is an outer QEMU policy, not a native LLVM performance knob.
# CMake may retain old global C/CXX flags in an existing CMakeCache.txt even
# after inherited CFLAGS/CXXFLAGS are unset. Clear those cache entries, while
# preserving the controlled Release flags and changing the installed ABI key.
assert 'unset CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS' in bootstrap
assert '    -DCMAKE_C_FLAGS=\n' in bootstrap
assert '    -DCMAKE_CXX_FLAGS=\n' in bootstrap
assert 'CMAKE_C_FLAGS=\nCMAKE_CXX_FLAGS=\n' in bootstrap
assert 'CPPFLAGS=' not in bootstrap[bootstrap.index('cmake_args=('):]

# The C++ language level is independent from release optimization. Keep C++23
# as the WHP native bootstrap baseline, require the requested level instead of
# silently falling back, and make it part of the installed-toolchain cache identity.
assert 'LLVM_CXX_STANDARD="${NATIVE_LLVM_CXX_STANDARD:-23}"' in bootstrap
assert 'compiler_supports_cxx_standard()' in bootstrap
assert '"-DCMAKE_CXX_STANDARD=$LLVM_CXX_STANDARD"' in bootstrap
assert '-DCMAKE_CXX_STANDARD_REQUIRED=ON' in bootstrap
assert 'CMAKE_CXX_STANDARD=$LLVM_CXX_STANDARD' in bootstrap
assert 'CMAKE_CXX_STANDARD_REQUIRED=ON' in bootstrap


# PCH is an actual LLVM target feature (LLVMSupport + dependent reuse), not
# merely a disabled CMake global flag. Exercise the bootstrap selection itself
# with hermetic compiler/cache identities; do not invoke a full LLVM build.
assert 'LLVM_PCH="${NATIVE_LLVM_PCH:-auto}"' in bootstrap
assert 'CMAKE_DISABLE_PRECOMPILE_HEADERS=$cmake_disable_precompile_headers' in bootstrap
assert '"-DCMAKE_DISABLE_PRECOMPILE_HEADERS=$cmake_disable_precompile_headers"' in bootstrap
# Avoid re-enabling cache launches through LLVM_CCACHE_BUILD/RULE_LAUNCH_COMPILE.
assert '-DLLVM_CCACHE_BUILD=OFF' in bootstrap
start = bootstrap.index('# WHP_NATIVE_LLVM_PCH_POLICY_BEGIN')
end = bootstrap.index('# WHP_NATIVE_LLVM_PCH_POLICY_END', start)
pch_policy = bootstrap[start:end]

for host, compiler, launcher, mode, disabled, expected_rc in (
    ('macos', 'Apple clang version 17.0.0', '', 'auto', 'OFF', 0),
    ('macos', 'Apple clang version 17.0.0', '/usr/bin/ccache', 'auto', 'OFF', 0),
    ('macos', 'Apple clang version 17.0.0', '/usr/bin/sccache', 'auto', 'OFF', 0),
    ('macos', 'clang version 19.1.0', '', 'auto', 'OFF', 0),
    ('macos', 'clang version 17.0.0', '', 'auto', 'ON', 0),
    ('macos', 'gcc (GCC) 15.1.0', '', 'auto', 'ON', 0),
    ('linux', 'clang version 20.0.0', '', 'auto', 'ON', 0),
    ('macos', 'Apple clang version 17.0.0', '', '0', 'ON', 0),
    ('macos', 'Apple clang version 17.0.0', '', '1', 'OFF', 0),
    ('macos', 'Apple clang version 17.0.0', '/usr/bin/sccache', '1', 'OFF', 0),
    ('macos', 'clang version 19.1.0', '/usr/bin/sccache', '1', 'OFF', 0),
    ('linux', 'clang version 20.0.0', '/usr/bin/sccache', 'auto', 'ON', 0),
    ('linux', 'clang version 20.0.0', '/usr/bin/sccache', '1', 'OFF', 0),
    ('macos', 'gcc (GCC) 15.1.0', '/usr/bin/sccache', 'auto', 'ON', 0),
):
    result = subprocess.run(
        ['bash', '-c', 'set -euo pipefail\n' +
         'cmake_compiler_launcher_args=("-DCMAKE_C_COMPILER_LAUNCHER=$compiler_cache_cmd" '
         '"-DCMAKE_CXX_COMPILER_LAUNCHER=$compiler_cache_cmd")\n' +
         pch_policy +
         '\nprintf "%s|%s|%s" "$cmake_disable_precompile_headers" '
         '"${cmake_compiler_launcher_args[0]}" "${cmake_compiler_launcher_args[1]}"'],
        env={
            'PATH': '/usr/bin:/bin',
            'host_os': host,
            'bootstrap_cxx_version': compiler,
            'compiler_cache_cmd': launcher,
            'LLVM_PCH': mode,
        },
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    assert result.returncode == expected_rc, (
        host, compiler, launcher, mode, result.stderr)
    assert expected_rc == 0, (host, compiler, launcher, mode)
    c_launcher = f'-DCMAKE_C_COMPILER_LAUNCHER={launcher}'
    # LLVM C++ compilation must not pass through sccache when PCH is on.
    # Non-PCH builds, including explicit opt-out, keep both launchers.
    cpp_launcher = ('-DCMAKE_CXX_COMPILER_LAUNCHER='
                    if launcher.endswith('/sccache') and disabled == 'OFF'
                    else f'-DCMAKE_CXX_COMPILER_LAUNCHER={launcher}')
    assert result.stdout == f'{disabled}|{c_launcher}|{cpp_launcher}', (
        host, compiler, launcher, mode, result.stdout)

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
assert 'BOOTSTRAP_SCHEMA=13' in bootstrap
for policy in runtime_off + runtime_on:
    assert policy in bootstrap[bootstrap.index('expected_marker='):], policy

print('native LLVM lean profile tests: passed')
