#!/usr/bin/env python3
"""Native LLVM: explicit macOS host and default targets, Darwin seed admission."""
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
assert 'macos_upgrade_native_llvm_triple' in s

block = s.split('llvm_host_triple="$bootstrap_cc_target_canonical"\n', 1)[1].split(
    '\n# The WHP LLVM fork is already', 1)[0]
assert 'macos_upgrade_native_llvm_triple' in block
assert 'llvm_default_target_triple="$llvm_host_triple"' in block

abi_helpers = (root / 'scripts/whp-build/macos-target-abi.bash').read_text()

for host_os, arch, version, seed, wanted in [
    ("macos", "arm64", "26.0", "aarch64-apple-darwin25.0.0", "aarch64-apple-macosx26.0"),
    ("macos", "arm64", "15.6", "aarch64-apple-darwin24.6", "aarch64-apple-macosx15.6"),
    ("macos", "arm64e", "27.2", "aarch64-apple-darwin27.2.0", "arm64e-apple-macosx27.2"),
    ("macos", "arm64e", "26.3", "arm64e-apple-darwin25.2.0", "arm64e-apple-macosx26.3"),
    ("macos", "x86_64", "13.7", "x86_64-apple-darwin22", "x86_64-apple-macosx13.7"),
    ("linux", "x86_64", "", "x86_64-unknown-linux-gnu", "x86_64-unknown-linux-gnu"),
]:
    setup = (
        f'host_os={host_os}\nhost_tag={arch}\ndeployment_target={version!r}\n'
        f'darwin_cmake_arch={arch!r}\n'
        f'bootstrap_cc_target_canonical={seed!r}\n'
    )
    result = subprocess.run(["bash", "-c", 'set -eu\n' + abi_helpers + setup +
                             'llvm_host_triple="$bootstrap_cc_target_canonical"\n' +
                             block + '\nprintf "%s|%s\\n" "$llvm_host_triple" '
                                     '"$llvm_default_target_triple"'],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == wanted + "|" + wanted, (
        host_os, arch, version, result.stdout, result.stderr)
    if host_os == "macos":
        assert "WHP native LLVM target upgrade:" in result.stderr

# Never rewrite untrusted or non-Apple Darwin triples to Apple macOS.
for bad_seed, selected, version in [
    ('aarch64-unknown-darwin27.2', 'arm64', '27.2'),
    ('aarch64-apple-ios27.2', 'arm64', '27.2'),
    ('aarch64-apple-darwin27.2-simulator', 'arm64', '27.2'),
    ('x86_64-apple-darwin25.0', 'arm64e', '26.0'),
    ('arm64e-apple-macosx27.2', 'arm64', '27.2'),
    ('aarch64-apple-darwin25.0', 'arm64', '10.15'),
    ('aarch64-apple-darwin25.0', 'arm64', 'invalid'),
]:
    result = subprocess.run(
        ['bash', '-c', 'set -euo pipefail\n' + abi_helpers +
         '\nmacos_upgrade_native_llvm_triple "$1" "$2" "$3"\n',
         '--', bad_seed, selected, version], capture_output=True, text=True)
    assert result.returncode != 0, (bad_seed, selected, result.stdout)


# A Darwin kernel triple and a macOS product triple may describe the same
# bootstrap ABI. Exercise the actual admission guard separately from the
# stricter installed-LLVM product-triple contract.
def bootstrap_function(name):
    start = s.index(f'\n{name}()\n{{') + 1
    end = s.index('\n}\n', start) + 3
    return s[start:end]


helpers = (root / 'scripts/whp-build/macos-target-abi.bash').read_text() + '\n'
helpers += '\n'.join(bootstrap_function(name) for name in (
    'canonical_native_arch', 'canonical_native_target_triple',
    'linux_target_abi_key', 'native_target_matches_host',
    'native_installed_target_matches_host', 'native_target_abi_key',
))
guard = '# Keep C and C++ on one host target ABI' + s.split(
    '# Keep C and C++ on one host target ABI', 1)[1].split(
        '\nnative_bootstrap_lp64_probe()', 1)[0]

for host_os, c_target, cxx_target, accepted in [
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-macosx27.2', True),
    ('macos', 'arm64-apple-macosx27.2', 'aarch64-apple-darwin27.2.0', True),
    ('macos', 'aarch64-apple-darwin25.2.0', 'aarch64-apple-macosx26.2', True),
    ('macos', 'aarch64-apple-darwin24.6.0', 'aarch64-apple-macosx15.6', True),
    ('macos', 'aarch64-apple-darwin19.6.0', 'aarch64-apple-macosx10.15.6', True),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-macosx27.3', False),
    ('macos', 'aarch64-apple-darwin27.2.1', 'aarch64-apple-macosx27.2', False),
    ('macos', 'aarch64-apple-darwin27.2.0', 'x86_64-apple-macosx27.2', False),
    # Unversioned Darwin/macOS seed identities are valid; deployment is
    # supplied explicitly by the native LLVM bootstrap.
    ('macos', 'aarch64-apple-darwin', 'aarch64-apple-macosx27.2', True),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-darwin', True),
    ('macos', 'aarch64-apple-macosx', 'aarch64-apple-macosx27.2', True),
    ('macos', 'aarch64-apple-darwin', 'aarch64-apple-macosx', True),
    ('macos', 'aarch64-apple-darwin', 'aarch64-apple-ios27.2', False),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-ios27.2', False),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-ios27.2-simulator', False),
    ('macos', 'aarch64-apple-darwin27.2.0', 'aarch64-apple-ios27.2-macabi', False),
    ('linux', 'x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-gnu', True),
    ('linux', 'x86_64-pc-linux-gnu', 'x86_64-unknown-linux-gnu', True),
    ('linux', 'amd64-linux-gnu', 'x86_64-unknown-linux-gnu', True),
    ('linux', 'x86_64-unknown-linux', 'x86_64-linux', True),
    ('linux', 'x86_64-unknown-linux-gnu', 'x86_64-unknown-linux-musl', False),
    ('linux', 'x86_64-unknown-linux-gnux32', 'x86_64-unknown-linux-gnux32', False),
    ('linux', 'x86_64-unknown-linux-gnu_ilp32', 'x86_64-unknown-linux-gnu_ilp32', False),
    ('linux', 'x86_64-unknown-linux-gnu-extra', 'x86_64-unknown-linux-gnu', False),
]:
    setup = (
        'set -euo pipefail\n'
        f'host_os={shlex.quote(host_os)}\n'
        'darwin_cmake_arch=arm64\n'
        f'host_tag={"aarch64" if host_os == "macos" else "x86_64"}\n'
        f'bootstrap_cc_target_canonical={shlex.quote(c_target)}\n'
        f'bootstrap_cxx_target_canonical={shlex.quote(cxx_target)}\n'
    )
    result = subprocess.run(
        ['bash', '-c', setup + helpers + '\n'
         + 'bootstrap_cc_target_canonical="$(canonical_native_target_triple '
           '"$bootstrap_cc_target_canonical")"\n'
         + 'bootstrap_cxx_target_canonical="$(canonical_native_target_triple '
           '"$bootstrap_cxx_target_canonical")"\n'
         + 'native_target_matches_host "$bootstrap_cc_target_canonical"\n'
         + 'native_target_matches_host "$bootstrap_cxx_target_canonical"\n'
         + guard],
        capture_output=True, text=True,
    )
    assert (result.returncode == 0) == accepted, (
        host_os, c_target, cxx_target, result.returncode, result.stderr)

# CPU generations within 32-bit x86 share the Linux calling ABI. This does
# not make 32-bit x86 a supported host for this LP64 LLVM bootstrap, and
# the original target triple still determines minimum ISA requirements.
key_probe = ('set -euo pipefail\n' + helpers + '\n'
             + 'host_os=linux\n'
             + 'native_target_abi_key "$1"\n')
for target in ('i386-linux-gnu', 'i486-pc-linux-gnu',
               'i586-unknown-linux-gnu', 'i686-linux-gnu'):
    result = subprocess.run(['bash', '-c', key_probe, '--', target],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'i386-linux-gnu', (target, result.stdout)

# A Darwin-family target does not imply an Apple vendor. The syntax parser
# retains distinct vendors and their original Darwin version numbers; it does
# not assert that their runtime/linker ABIs are interchangeable.
darwin_identity_probe = ('set -euo pipefail\n' + helpers + '\n'
                         + 'darwin_target_identity "$1"\n')
for triple, expected in (
    ('arm64-apple-darwin24.0.0', 'aarch64-apple-darwin24.0.0'),
    ('arm64-unknown-darwin24.0.0', 'aarch64-unknown-darwin24.0.0'),
    ('arm64-pc-darwin24.0.0', 'aarch64-pc-darwin24.0.0'),
    ('arm64e-custom-darwin27.1', 'arm64e-custom-darwin27.1'),
    ('arm64-unknown-macosx15.0', 'aarch64-unknown-macosx15.0'),
    ('x86_64-unknown-darwin', 'x86_64-unknown-darwin'),
):
    result = subprocess.run(['bash', '-c', darwin_identity_probe, '--', triple],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected, (triple, result.stdout)

for triple in (
    'arm64-unknown-ios18.0',
    'arm64--darwin24.0',
    'arm64-unknown-darwin24.0-simulator',
    'arm64-unknown-macosx15.0-macabi',
    'arm64-unknown-darwin24.0.0.0',
):
    result = subprocess.run(['bash', '-c', darwin_identity_probe, '--', triple],
                            capture_output=True, text=True)
    assert result.returncode != 0, (triple, result.stdout)

# Apple arm64e has a distinct pointer-authentication ABI. It must remain
# different from ordinary arm64 even when the OS/version spelling agrees.
macos_key_probe = ('set -euo pipefail\n' + helpers + '\n'
                   + 'macos_target_abi_key "$1"\n')
for triple, expected in (
    ('arm64-apple-macosx27.2', 'aarch64-apple-macosx27.2.0'),
    ('arm64e-apple-macosx27.2', 'arm64e-apple-macosx27.2.0'),
    ('arm64e-apple-darwin27.2.0', 'arm64e-apple-macosx27.2.0'),
):
    result = subprocess.run(['bash', '-c', macos_key_probe, '--', triple],
                            capture_output=True, text=True, check=True)
    assert result.stdout.strip() == expected, (triple, result.stdout)

# Installed Clang/Clang++ must not report generic Darwin after LLVM has
# been configured for a specific macOS product/deployment target. The seed
# acceptance tested above is intentionally less strict.
assert s.count('native_installed_target_matches_host "$target" || {') == 2
installed_target_probe = ('set -euo pipefail\n' + helpers + '\n'
                          'host_os=macos\n'
                          'host_tag="$2"\n'
                          'darwin_cmake_arch="$3"\n'
                          'native_installed_target_matches_host "$1"\n')
for triple, arch, selected, accepted in (
    ('aarch64-apple-macosx27.3', 'aarch64', 'arm64', True),
    ('arm64-apple-macosx27.3.0', 'aarch64', 'arm64', True),
    ('arm64e-apple-macosx27.3', 'aarch64', 'arm64e', True),
    ('aarch64-apple-macosx27.3', 'aarch64', 'arm64e', False),
    ('arm64e-apple-macosx27.3', 'aarch64', 'arm64', False),
    ('x86_64-apple-macosx15.6', 'x86_64', 'x86_64', True),
    ('aarch64-apple-darwin27.3.0', 'aarch64', 'arm64', False),
    ('aarch64-apple-darwin', 'aarch64', 'arm64', False),
    ('aarch64-apple-macosx', 'aarch64', 'arm64', False),
    ('aarch64-apple-ios27.3', 'aarch64', 'arm64', False),
    ('aarch64-apple-macosx27.3-simulator', 'aarch64', 'arm64', False),
):
    result = subprocess.run(
        ['bash', '-c', installed_target_probe, '--', triple, arch, selected],
        capture_output=True, text=True,
    )
    assert (result.returncode == 0) == accepted, (
        triple, result.returncode, result.stderr,
    )

# Keep the compiler-rt, native LLVM default, and platform checks distinct.
assert '"-DLLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple"' in s
assert '"-DLLVM_HOST_TRIPLE=$llvm_host_triple"' in s
assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in s
if cmake.is_file():  # Submodule may not be initialized in standalone CI.
    llvm = cmake.read_text()
    assert "LLVM_MACOS_EXPLICIT_DEFAULT_TRIPLE" in llvm
    assert "CMAKE_OSX_DEPLOYMENT_TARGET" in llvm
print("Native LLVM explicit macOS host/default triples: verified")
