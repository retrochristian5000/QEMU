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

# A cached compiler must exercise the frontend, IR verifier, and backend before
# reuse.  --version alone cannot detect mixed LLVM objects such as a verifier
# that rejects an attribute emitted by the matching Clang frontend.
assert '"$prefix/bin/clang" -x c -c - -o /dev/null' in bootstrap
assert '"$prefix/bin/clang++" -x c++ -c - -o /dev/null' in bootstrap

# Darwin ABI identity is more than the CPU name.  A native compiler cache must
# retain the producer triple and reject a compiler that no longer targets the
# Apple Darwin/macOS ABI even when its architecture still matches the host.
assert 'BOOTSTRAP_CC_TARGET_TRIPLE=$bootstrap_cc_target' in bootstrap
assert 'native_target_matches_host "$target"' in bootstrap
assert 'darwin*|macos*|macosx*' in bootstrap
assert 'apple' in bootstrap

# Never carry a CMake/Ninja object graph across a native LLVM rebuild.  LLVM
# source revisions can change IR contracts, so an incremental graph from an
# older revision is not a safe cache boundary.
assert 'rm -rf "$LLVM_BUILD_DIR"' in bootstrap

print('native LLVM wiring tests: passed')
