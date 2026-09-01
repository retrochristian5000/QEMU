#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
config = (ROOT / 'scripts/whp-config/config.py').read_text(encoding='utf-8')
build = (ROOT / 'build.sh').read_text(encoding='utf-8')
bootstrap = (ROOT / 'scripts/bootstrap-native-clang.sh').read_text(encoding='utf-8')
i386_bootstrap = (ROOT / 'scripts/bootstrap-i386-clang.sh').read_text(encoding='utf-8')
powerpc_bootstrap = (ROOT / 'scripts/bootstrap-powerpc-clang-base.sh').read_text(encoding='utf-8')
inventory = (ROOT / 'scripts/whp-build/shell-inventory.bash').read_text(encoding='utf-8')
macos_workflow = (ROOT / '.github/workflows/native-llvm-macos.yml').read_text(encoding='utf-8')

assert "Option('BOOTSTRAP_NATIVE_LLVM', 'Host features'" in config
assert 'scripts/bootstrap-native-clang.sh' in build
assert 'CC="$NATIVE_LLVM_DIR/bin/clang"' in build
assert 'CXX="$NATIVE_LLVM_DIR/bin/clang++"' in build
assert 'toolchains/llvm-project' in bootstrap
assert 'git clone' not in bootstrap
assert '-DLLVM_ENABLE_PROJECTS=clang' in bootstrap
assert 'clang;clang-resource-headers' in bootstrap
assert 'bootstrap-native-clang.sh' in inventory

# Darwin Clang passes -lto_library <InstalledDir>/../lib/libLTO.dylib to ld64
# when LTO is active. A Clang-only distribution therefore creates a producer /
# consumer mismatch: WHP Clang emits current LLVM bitcode but the linker cannot
# load a matching reader. Keep libLTO in the macOS native distribution, record
# that component in the cache contract, and reject cached toolchains missing it.
assert 'llvm_distribution_components="${llvm_distribution_components};LTO"' in bootstrap
assert 'LLVM_DISTRIBUTION_COMPONENTS=$llvm_distribution_components' in bootstrap
assert '[[ -f "$prefix/lib/libLTO.dylib" ]] || return 1' in bootstrap

# A Darwin Clang driver accepts -fsanitize=undefined even when its matching
# compiler-rt runtime was never built or installed. Native macOS toolchains must
# therefore build compiler-rt with the just-built Clang, generate the runtimes
# graph, distribute both builtins and runtimes, and prove the installed driver
# can link an actual UBSan executable. Linux keeps its existing no-runtimes
# profile unless it is deliberately opted in later.
assert 'llvm_enable_runtimes=compiler-rt' in bootstrap
assert 'llvm_include_runtimes=ON' in bootstrap
assert '${llvm_distribution_components};LTO;builtins;runtimes' in bootstrap
assert '"-DLLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes"' in bootstrap
assert '"-DLLVM_INCLUDE_RUNTIMES=$llvm_include_runtimes"' in bootstrap
assert 'LLVM_ENABLE_RUNTIMES=$llvm_enable_runtimes' in bootstrap
assert '-fsanitize=undefined' in bootstrap
assert '-fsanitize=undefined' in macos_workflow
assert 'BOOTSTRAP_SCHEMA=4' in bootstrap

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

# A cached compiler must exercise the frontend, resource headers, IR verifier,
# and backend before reuse. --version alone cannot detect mixed LLVM objects
# such as a verifier that rejects an attribute emitted by matching Clang.
assert '"$prefix/bin/clang" -x c -c - -o /dev/null' in bootstrap
assert '#include <stddef.h>' in bootstrap
assert '#include <stdarg.h>' in bootstrap
assert '-fno-omit-frame-pointer -momit-leaf-frame-pointer' in bootstrap
assert '"$prefix/bin/clang++" -x c++ -c - -o /dev/null' in bootstrap

# Native ABI identity is more than the CPU name. On macOS, follow LLVM's
# ARCH-VENDOR-OS[-ENV] boundary: `apple` must be the vendor field and the OS
# field must be Darwin/macOS. A loose `*-apple-darwin*` substring would accept
# malformed triples such as arm64-unknown-apple-darwin.
assert 'native_target_matches_host "$target"' in bootstrap
assert "IFS='-' read -r arch target_vendor target_os _ <<< \"$target\"" in bootstrap
assert '[[ "$target_vendor" == apple ]] || return 1' in bootstrap
assert 'darwin*|macos*)' in bootstrap
for loose_match in ('*-apple-darwin*', '*-apple-macos*', '*-apple-macosx*'):
    assert loose_match not in bootstrap
assert '*-linux-*|*-linux' in bootstrap

# Do not pass CMake cache variables that the pinned LLVM revision no longer
# defines. CMake reports these as manually-specified variables that were not
# used by the project, which hides meaningful bootstrap warnings in noise.
assert 'CLANG_ENABLE_ARCMT' not in bootstrap
for llvm_bootstrap in (bootstrap, i386_bootstrap, powerpc_bootstrap):
    assert 'LLVM_ENABLE_TERMINFO' not in llvm_bootstrap

# LLVM's large executable links need their own Ninja pool. Keep compilation
# fully parallel while capping concurrent links so a many-core host does not
# turn link-time memory pressure into paging or intermittent bootstrap failure.
link_job_policies = (
    (bootstrap, 'NATIVE_LLVM_LINK_JOBS'),
    (i386_bootstrap, 'I386_LLVM_LINK_JOBS'),
    (powerpc_bootstrap, 'POWERPC_LLVM_LINK_JOBS'),
)
for llvm_bootstrap, override in link_job_policies:
    assert f'LLVM_LINK_JOBS="${{{override}:-2}}"' in llvm_bootstrap
    assert 'LLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS' in llvm_bootstrap
    assert f'{override} must be a positive integer' in llvm_bootstrap

# Never carry a CMake/Ninja object graph across a native LLVM rebuild. LLVM
# source revisions can change IR contracts, so an incremental graph from an
# older revision is not a safe cache boundary.
assert 'rm -rf "$LLVM_BUILD_DIR"' in bootstrap

print('native LLVM wiring tests: passed')