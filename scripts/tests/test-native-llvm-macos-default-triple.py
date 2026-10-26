#!/usr/bin/env python3
"""Native LLVM: explicit macOS target, separate Darwin host identity."""
from pathlib import Path
import subprocess
import shlex

root = Path(__file__).resolve().parents[2]
s = (root / "scripts/bootstrap-native-clang.bash").read_text()
cmake = (root / "toolchains/llvm-project/llvm/CMakeLists.txt")
assert "-DLLVM_MACOS_EXPLICIT_DEFAULT_TRIPLE=ON" in s
assert "-DLLVM_MACOS_HOST_SDK_RESOLVE=ON" in s
assert '"-DCMAKE_OSX_SYSROOT=$sdkroot"' in s
assert 'MacOSX*.sdk) ;;' in s
assert 'llvm_host_triple="$bootstrap_cc_target_canonical"' in s

block = s.split('llvm_host_triple="$bootstrap_cc_target_canonical"\n', 1)[1].split(
    '\n# The WHP LLVM fork is already', 1)[0]
assert 'llvm_default_target_triple="$host_tag-apple-macosx$deployment_target"' in block
assert 'else\n    llvm_default_target_triple="$llvm_host_triple"\nfi' in block

for host_os, arch, version, seed, wanted in [
    ("macos", "aarch64", "26.0", "aarch64-apple-darwin25.0.0", "aarch64-apple-macosx26.0"),
    ("macos", "aarch64", "15.6", "aarch64-apple-darwin24.6", "aarch64-apple-macosx15.6"),
    ("macos", "x86_64", "13.7", "x86_64-apple-darwin22", "x86_64-apple-macosx13.7"),
    ("linux", "x86_64", "", "x86_64-unknown-linux-gnu", "x86_64-unknown-linux-gnu"),
]:
    setup = (
        f'host_os={host_os}\nhost_tag={arch}\ndeployment_target={version!r}\n'
        f'bootstrap_cc_target_canonical={seed!r}\n'
    )
    result = subprocess.run(["bash", "-c", setup + 'set -eu\n' +
                             'llvm_host_triple="$bootstrap_cc_target_canonical"\n' +
                             block + '\nprintf "%s|%s\\n" "$llvm_host_triple" '
                                     '"$llvm_default_target_triple"'],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == seed + "|" + wanted, (
        host_os, version, result.stdout, result.stderr)

# A Darwin kernel triple and a macOS product triple may describe the same
# native ABI. Exercise the actual bootstrap guard rather than assuming its
# raw reported target strings must be identical.
helpers = 'canonical_native_arch()\n' + s.split(
    'canonical_native_arch()\n', 1)[1].split(
        '\nbootstrap_cc_target="$(query_target_triple', 1)[0]
guard = '# Keep C and C++ on one host target ABI' + s.split(
    '# Keep C and C++ on one host target ABI', 1)[1].split(
        '\n# The bootstrap compiler may report', 1)[0]

for host_os, c_target, cxx_target, accepted in [
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-macosx27.2', True),
    ('macos', 'arm64-apple-macosx27.2', 'aarch64-apple-darwin27.2.0', True),
    ('macos', 'aarch64-apple-darwin25.2.0', 'aarch64-apple-macosx26.2', True),
    ('macos', 'aarch64-apple-darwin24.6.0', 'aarch64-apple-macosx15.6', True),
    ('macos', 'aarch64-apple-darwin19.6.0', 'aarch64-apple-macosx10.15.6', True),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-macosx27.3', False),
    ('macos', 'aarch64-apple-darwin27.2.1', 'aarch64-apple-macosx27.2', False),
    ('macos', 'aarch64-apple-darwin27.2.0', 'x86_64-apple-macosx27.2', False),
    ('linux', 'x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-gnu', True),
    ('linux', 'x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-musl', False),
]:
    setup = (
        'set -euo pipefail\n'
        f'host_os={shlex.quote(host_os)}\n'
        f'bootstrap_cc_target_canonical={shlex.quote(c_target)}\n'
        f'bootstrap_cxx_target_canonical={shlex.quote(cxx_target)}\n'
    )
    result = subprocess.run(
        ['bash', '-c', setup + helpers + '\n'
         + 'bootstrap_cc_target_canonical="$(canonical_native_target_triple '
           '"$bootstrap_cc_target_canonical")"\n'
         + 'bootstrap_cxx_target_canonical="$(canonical_native_target_triple '
           '"$bootstrap_cxx_target_canonical")"\n'
         + guard],
        capture_output=True, text=True,
    )
    assert (result.returncode == 0) == accepted, (
        host_os, c_target, cxx_target, result.returncode, result.stderr)

# Keep the compiler-rt, native LLVM default, and platform checks distinct.
assert '"-DLLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple"' in s
assert '"-DLLVM_HOST_TRIPLE=$llvm_host_triple"' in s
assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in s
if cmake.is_file():  # Submodule may not be initialized in standalone CI.
    llvm = cmake.read_text()
    assert "LLVM_MACOS_EXPLICIT_DEFAULT_TRIPLE" in llvm
    assert "CMAKE_OSX_DEPLOYMENT_TARGET" in llvm
print("Native LLVM macOS default-triple separation: verified")
