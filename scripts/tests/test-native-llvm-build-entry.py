#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
build = (ROOT / "build.sh").read_text(encoding="utf-8")
runtime_entry = ROOT / "builder.sh"

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

print("native LLVM build-entry handshake test: passed")
