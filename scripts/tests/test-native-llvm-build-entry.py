#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
build = (ROOT / "build.sh").read_text(encoding="utf-8")
runtime_entry = ROOT / "builder.sh"
portable_entry = ROOT / "scripts/whp-build/portable-build-entry.py"

# BOOTSTRAP_NATIVE_LLVM is selected at the public build boundary, but the
# compiler only matters if that same invocation can reach QEMU's real Bash
# runner.  A stale/nonexistent handoff path lets LLVM bootstrap successfully
# and then fails before QEMU configure ever consumes CC/CXX.
assert runtime_entry.is_file(), "root builder.sh is the runtime Bash consumer"
assert '"$SOURCE_DIR/builder.sh"' in build, (
    "build.sh must hand non-macOS builds to the existing root builder.sh"
)
assert 'scripts/whp-build/build-entry.bash' not in build, (
    "build.sh references a nonexistent runtime handoff"
)

bootstrap_index = build.index('scripts/bootstrap-native-clang.sh')
runtime_index = build.index('"$SOURCE_DIR/builder.sh"')
assert bootstrap_index < runtime_index, (
    "native LLVM must be selected before QEMU's runtime build consumer"
)

# The portable Python core cannot currently run the native LLVM bootstrap.
# An explicit request must therefore fail closed instead of silently building
# QEMU with the system compiler and violating the selected compiler policy.
env = os.environ.copy()
env.update({
    'WHP_PORTABLE_PROBE_ONLY': '1',
    'BUILD_QEMU_IMG': '0',
    'BUILD_QEMU_SYSTEM_I386': '0',
    'BUILD_QEMU_SYSTEM_PPC': '0',
    'BUILD_QEMU_SYSTEM_SPARC': '0',
    'BUILD_OPENBIOS': 'auto',
    'BOOTSTRAP_POWERPC_TOOLCHAIN': 'auto',
    'BOOTSTRAP_NATIVE_LLVM': '1',
})
portable_probe = subprocess.run(
    [sys.executable, str(portable_entry)],
    text=True,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    check=False,
    env=env,
)
assert portable_probe.returncode != 0, (
    "portable core silently ignored explicit BOOTSTRAP_NATIVE_LLVM=1"
)
assert 'BOOTSTRAP_NATIVE_LLVM' in portable_probe.stderr, portable_probe.stderr

print("native LLVM build-entry handshake test: passed")
