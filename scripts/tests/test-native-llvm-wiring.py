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

print('native LLVM wiring tests: passed')
