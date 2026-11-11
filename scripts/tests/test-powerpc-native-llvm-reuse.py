#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression gates for reusing the native LLVM in PowerPC/OpenBIOS builds."""

from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[2]
orchestrator = ROOT / "scripts/bootstrap-powerpc-clang.bash"
shared = ROOT / "scripts/bootstrap-powerpc-clang-shared.bash"
native = ROOT / "scripts/bootstrap-native-clang.bash"
base = ROOT / "scripts/bootstrap-powerpc-clang-base.bash"
driver = ROOT / "scripts/whp-build/powerpc-clang-driver.bash"
build = ROOT / "build.sh"

for path in (orchestrator, shared, native, base, driver):
    subprocess.run(["bash", "-n", str(path)], check=True)

source = orchestrator.read_text(encoding="utf-8")
implementation = shared.read_text(encoding="utf-8")
host = native.read_text(encoding="utf-8")
standalone = base.read_text(encoding="utf-8")
wrapper = driver.read_text(encoding="utf-8")
entry = build.read_text(encoding="utf-8")

assert "LLVM_TARGETS_TO_BUILD='AArch64;X86;PowerPC'" in host
assert "LLD_ENABLE_BACKENDS='ELF;COFF;MinGW;MachO'" in host
assert 'WHP_SHARED_LLVM_DIR="$NATIVE_LLVM_DIR"' in entry
assert "export NATIVE_LLVM_DIR WHP_SHARED_LLVM_DIR" in entry

shared_gate = 'if [[ -n "${WHP_SHARED_LLVM_DIR:-${NATIVE_LLVM_DIR:-}}" ]]; then'
shared_call = 'bash "$SCRIPT_DIR/bootstrap-powerpc-clang-shared.bash"'
assert shared_gate in source
assert shared_call in source
assert source.index(shared_call) < source.index(
    'bash "$SCRIPT_DIR/bootstrap-powerpc-llvm-source-cache.sh"'
)
assert 'bash "$BASE_BOOTSTRAP"' in source  # standalone remains available

assert 'grep -Fxq "LLVM_GIT_COMMIT=$llvm_revision"' in implementation
assert "LLVM_TARGETS_TO_BUILD=AArch64;X86;PowerPC" in implementation
assert "LLD_ENABLE_BACKENDS=ELF;COFF;MinGW;MachO" in implementation
assert 'git -C "$SOURCE_DIR" ls-tree HEAD -- "$LLVM_SUBMODULE_PATH"' in implementation
assert 'git -C "$llvm_source" rev-parse HEAD' in implementation
assert 'ln -s "$SHARED_LLVM_DIR" "$staged_toolchain/llvm"' in implementation
assert 'LLVM_EXECUTABLE_SOURCE=shared:$SHARED_LLVM_DIR' in implementation
assert 'powerpc-elf' in implementation
assert 'ELF32' in implementation and 'big endian' in implementation
assert '"$toolchain/bin/$TOOLCHAIN_TARGET-ld"' in implementation
assert 'for phase in llvm-ar llvm-mc llvm-nm llvm-strip' in implementation
assert 'old_moved=1' in implementation
assert 'if ((status != 0))' in implementation
for forbidden in ("cmake --build", "cmake -S", "git clone",
                  'rm -rf "$SHARED_LLVM_DIR"', 'mv "$SHARED_LLVM_DIR"'):
    assert forbidden not in implementation, forbidden

assert 'cp "$SCRIPT_DIR/whp-build/powerpc-clang-driver.bash"' in standalone
assert 'cp "$SCRIPT_DIR/whp-build/powerpc-clang-driver.bash"' in implementation
assert "exec \"$clang\"" in wrapper
assert "--target=powerpc-none-elf" in wrapper
assert "-mcall-sysv-noeabi" in wrapper

print("PowerPC native LLVM reuse, provenance, fallback, and rollback gates passed")
