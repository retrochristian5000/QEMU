#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / 'scripts' / 'bootstrap-native-clang.bash'

text = BOOTSTRAP.read_text(encoding='utf-8')

# Native LLVM is a host tool, so its Darwin architecture policy is independent
# from QEMU TCG's WHP_MACOS_ARCH=auto safety gate. Apple Silicon auto must
# always use the normal macOS arm64 ABI, even when arm64e is available.
# Explicit arm64e remains gated by C/C++ ABI + pointer-authentication probes.
assert 'NATIVE_LLVM_MACOS_ARCH' in text
assert 'compiler_supports_macos_arch()' in text
assert 'sdk_real_path="$(cd "$sdkroot" && pwd -P)" || exit 1' in text
assert 'MacOSX*.sdk) ;;' in text
assert 'native LLVM host build requires a MacOSX.sdk' in text
# Even a successfully executed arm64e main() can conceal missing compiler
# pointer-authentication semantics. Both C and C++ probes must check the ABI
# and exercise an authenticated indirect function-pointer call.
arch_probe = text.split('compiler_supports_macos_arch()', 1)[1].split(
    'if [[ "$host_os" == macos ]]; then', 1
)[0]
assert 'if [[ "$arch" == arm64e ]]; then' in arch_probe
assert '#if !defined(__arm64e__) || !defined(__PTRAUTH__)' in arch_probe
assert '#if !__has_feature(ptrauth_calls)' in arch_probe
assert 'int (*volatile callback)(void)' in arch_probe
assert 'return callback();' in arch_probe
assert 'requested_macos_arch="${NATIVE_LLVM_MACOS_ARCH:-auto}"' in text
arch_selection = text.split('case "$requested_macos_arch" in', 2)[2]
auto_block = arch_selection.split('auto)', 1)[1].split(';;', 1)[0]
assert 'darwin_cmake_arch=arm64' in auto_block
assert 'darwin_cmake_arch=arm64e' not in auto_block
assert 'compiler_supports_macos_arch' not in auto_block
assert 'if ! compiler_supports_macos_arch "$bootstrap_cc" c "$darwin_cmake_arch"' in text
assert 'if ! compiler_supports_macos_arch "$bootstrap_cxx" c++ "$darwin_cmake_arch"' in text
assert 'darwin_cmake_arch=arm64e' in text
assert 'darwin_cmake_arch=arm64' in text
assert 'WHP native LLVM macOS arch:' in text
# Unlike the QEMU wrapper, a direct LLVM bootstrap used to have no explicit
# Apple Silicon macOS 11 deployment floor before CMake and compiler-rt.
assert '"$host_tag" == aarch64' in text
assert '10#${deployment_target%%.*} < 11' in text
assert 'native LLVM arm64/arm64e deployment target must be macOS 11.0 or newer' in text

assert '"$output" >/dev/null 2>&1' in text

# The selected Mach-O ABI must be part of the cached toolchain identity so an
# older arm64 toolchain cannot be reused after an arm64e-capable host switches.
assert 'MACOS_BOOTSTRAP_ARCH=$darwin_cmake_arch' in text

# CMake's parent graph and compiler-rt ExternalProjects must consume the same
# selected architecture; otherwise clang could be arm64e while its runtimes are
# silently built for a different ABI.
assert text.count('-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch') >= 2

# LLVM's CMake-side check must consume CMake's configured Apple target and
# effective compiler predefines, not infer an arm64e ABI from host hardware.
llvm_cmake = ROOT / 'toolchains' / 'llvm-project' / 'llvm' / 'CMakeLists.txt'
llvm_config = ROOT / 'toolchains' / 'llvm-project' / 'llvm' / 'cmake' / 'config-ix.cmake'
if llvm_cmake.is_file() and llvm_config.is_file():
    cmake_text = llvm_cmake.read_text(encoding='utf-8')
    config_text = llvm_config.read_text(encoding='utf-8')
    assert 'CMAKE_SYSTEM_NAME STREQUAL "Darwin"' in cmake_text
    assert 'NOT CMAKE_CROSSCOMPILING' in cmake_text
    assert 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64e"' in cmake_text
    assert 'CMAKE_OSX_ARCHITECTURES STREQUAL "arm64"' in cmake_text
    assert 'CMAKE_OSX_ARCHITECTURES STREQUAL "x86_64"' in cmake_text
    assert '#if !defined(__arm64e__) || !defined(__PTRAUTH__)' in cmake_text
    assert 'check_cxx_source_compiles' in cmake_text
    assert 'LLVM_HOST_TRIPLE' in config_text
    assert 'CMAKE_HOST_APPLE AND CMAKE_SYSTEM_NAME STREQUAL "Darwin"' in config_text
    assert 'Native macOS LLVM host triple must describe macOS/Darwin' in config_text

# Apple compiler-rt's SME assembly path uses the armv8a+sme driver spelling.
# Do not normalize it to armv8-a+sme: that form is accepted in other AArch64
# parser contexts but is rejected by the Apple compiler-rt build path.
compiler_rt_builtins = (
    ROOT / 'toolchains' / 'llvm-project' / 'compiler-rt' / 'lib' / 'builtins'
    / 'CMakeLists.txt'
)
if compiler_rt_builtins.is_file():
    compiler_rt_text = compiler_rt_builtins.read_text(encoding='utf-8')
    assert '-march=armv8a+sme' in compiler_rt_text
    assert '-march=armv8-a+sme' not in compiler_rt_text

# The installed compiler must be smoke-tested with the ABI selected for the
# toolchain itself.  A plain clang invocation defaults back to arm64 on macOS
# and would therefore fail to prove that an arm64e bootstrap can compile C.
assert 'smoke_arch_args=(' in text
assert '-arch "$darwin_cmake_arch"' in text
assert '"${smoke_arch_args[@]}"' in text
assert '#ifndef __arm64e__' in text
assert 'whp_arm64e_fp' in text
assert '#if !defined(__PTRAUTH__) || !__has_feature(ptrauth_calls)' in text
assert 'whp_arm64e_cxx_smoke' in text

# LLD ARM64e support is admitted by an authenticated-relocation link probe,
# not by architecture spelling, a trivial link, or an old blanket prohibition.
assert 'whp_bootstrap_arm64e_lld_auth_probe()' in text
assert 'WHP_ARM64E_USE_LLD="${WHP_ARM64E_USE_LLD:-0}"' in text
probe = (ROOT / 'scripts' / 'whp-build' / 'arm64e-lld-probe.bash').read_text(encoding='utf-8')
assert 'arm64e-lld-probe.bash' in text
assert '.quad _whp_auth_target@AUTH(ia,42,addr)' in probe
assert 'DYLD_CHAINED_PTR_ARM64E_USERLAND24' in probe
# The otool-style driver shares llvm-objdump's decoder and should provide a
# second public Mach-O inspection interface without replacing PAC bit tests.
assert 'llvm-otool' in probe
assert ' -chained_fixups ' in probe
assert ' -dyld_info ' in probe
assert 'bootstrap_lld_arch_ok=0' in text
assert '"$WHP_ARM64E_USE_LLD" == 1' in text
assert '"$bootstrap_lld_arch_ok" == 1' in text
assert text.index('whp_bootstrap_arm64e_lld_auth_probe()') < text.index('-fuse-ld=lld')

print('native LLVM arm64e bootstrap policy: verified')
