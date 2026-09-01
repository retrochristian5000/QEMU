#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
config = (ROOT / 'scripts/whp-config/config.py').read_text(encoding='utf-8')
build = (ROOT / 'build.sh').read_text(encoding='utf-8')
bootstrap = (ROOT / 'scripts/bootstrap-native-clang.sh').read_text(encoding='utf-8')
inventory = (ROOT / 'scripts/whp-build/shell-inventory.bash').read_text(encoding='utf-8')

assert "Option('BOOTSTRAP_NATIVE_LLVM', 'Host features'" in config
assert 'scripts/bootstrap-native-clang.sh' in build
assert 'CC="$NATIVE_LLVM_DIR/bin/clang"' in build
assert 'CXX="$NATIVE_LLVM_DIR/bin/clang++"' in build
assert 'toolchains/llvm-project' in bootstrap
assert 'git clone' not in bootstrap
assert '-DLLVM_ENABLE_PROJECTS=clang' in bootstrap
assert 'clang;clang-resource-headers' in bootstrap
assert 'bootstrap-native-clang.sh' in inventory

# The public build entry owns platform detection. Native LLVM consumes the same
# normalized OS/kernel/architecture identity instead of making an independent
# platform decision that can drift from QEMU's wrapper selection.
for host_os in ('macos', 'linux', 'windows'):
    assert f'WHP_HOST_OS={host_os}' in build
assert 'export WHP_HOST_OS WHP_HOST_KERNEL WHP_HOST_ARCH' in build
assert 'host_os="${WHP_HOST_OS:-}"' in bootstrap
assert 'HOST_OS=$host_os' in bootstrap
assert 'HOST_KERNEL=$host_kernel' in bootstrap
assert 'HOST_ARCH=$host_arch' in bootstrap
assert 'BOOTSTRAP_SCHEMA=2' in bootstrap

# A cached compiler must exercise the frontend, resource headers, IR verifier,
# and backend before reuse. --version alone cannot detect mixed LLVM objects
# such as a verifier that rejects an attribute emitted by matching Clang.
assert '"$prefix/bin/clang" -x c -c - -o /dev/null' in bootstrap
assert '#include <stddef.h>' in bootstrap
assert '#include <stdarg.h>' in bootstrap
assert '-fno-omit-frame-pointer -momit-leaf-frame-pointer' in bootstrap
assert '"$prefix/bin/clang++" -x c++ -c - -o /dev/null' in bootstrap

# Native ABI identity is more than the CPU name. Require an Apple target on
# macOS and a Linux target on Linux so a same-architecture cross compiler cannot
# masquerade as the host compiler.
assert 'native_target_matches_host "$target"' in bootstrap
for target in ('*-apple-darwin*', '*-apple-macos*', '*-apple-macosx*'):
    assert target in bootstrap
assert '*-linux-*|*-linux' in bootstrap

# Never carry a CMake/Ninja object graph across a native LLVM rebuild. LLVM
# source revisions can change IR contracts, so an incremental graph from an
# older revision is not a safe cache boundary.
assert 'rm -rf "$LLVM_BUILD_DIR"' in bootstrap

print('native LLVM wiring tests: passed')
