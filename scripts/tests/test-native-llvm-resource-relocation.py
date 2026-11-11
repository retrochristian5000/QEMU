#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Reject foreign/forgotten Clang headers; keep post-publish validation."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
bootstrap = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(encoding="utf-8")
start = bootstrap.index("\nnative_neon_headers_usable()\n{") + 1
end = bootstrap.index("\n}\n", start) + 3
helper = bootstrap[start:end]

driver = """#!/bin/sh
if [ "${1:-}" = -print-resource-dir ]; then
    case "$0" in
        */clang++) printf '%s\\n' "$WHP_CXX_RESOURCE" ;;
        *) printf '%s\\n' "$WHP_C_RESOURCE" ;;
    esac
    exit 0
fi
for arg in "$@"; do
    if [ "$arg" = - ]; then cat >/dev/null; fi
done
exit 0
"""

with tempfile.TemporaryDirectory(prefix="whp-clang-resource-") as temporary:
    root = Path(temporary)
    prefix = root / "llvm"
    bindir = prefix / "bin"
    headers = prefix / "lib" / "clang" / "mock" / "include"
    headers.mkdir(parents=True)
    bindir.mkdir()
    for name in ("clang", "clang++"):
        tool = bindir / name
        tool.write_text(driver, encoding="utf-8")
        tool.chmod(0o755)
    for header in ("arm_neon.h", "arm_bf16.h", "arm_vector_types.h"):
        (headers / header).write_text("/* fixture */\n", encoding="utf-8")
    foreign = root / "foreign" / "include"
    foreign.mkdir(parents=True)
    for header in ("arm_neon.h", "arm_bf16.h", "arm_vector_types.h"):
        (foreign / header).write_text("/* external fixture */\n", encoding="utf-8")

    probe = "\n".join([
        "set -euo pipefail",
        "host_os=macos",
        "host_tag=aarch64",
        "darwin_cmake_arch=arm64e",
        "sdkroot=/mock/MacOSX.sdk",
        "deployment_target=15.0",
        'native_llvm_validation_error() { printf "resource error: %s\\n" "$2" >&2; }',
        helper,
        'native_neon_headers_usable "$1"',
    ])

    def run(c_resource, cxx_resource):
        env = os.environ.copy()
        env.update(WHP_C_RESOURCE=str(c_resource),
                   WHP_CXX_RESOURCE=str(cxx_resource))
        return subprocess.run(["bash", "-c", probe, "--", str(prefix)],
                              env=env, text=True, capture_output=True)

    resource = headers.parent
    valid = run(resource, resource)
    assert valid.returncode == 0, valid.stderr

    wrong = run(foreign.parent, foreign.parent)
    assert wrong.returncode != 0
    assert "outside toolchain" in wrong.stderr, wrong.stderr

    split = run(resource, foreign.parent)
    assert split.returncode != 0
    assert "disagree on resource directory" in split.stderr, split.stderr

    missing = run(root / "missing", root / "missing")
    assert missing.returncode != 0
    assert "resource directory is absent" in missing.stderr, missing.stderr

    (headers / "arm_neon.h").unlink()
    missing_header = run(resource, resource)
    assert missing_header.returncode != 0
    assert "missing generated NEON header" in missing_header.stderr

# Publish only after a second check of relocated resource paths, preserving
# the previous installation on failure.
post = bootstrap.index('if ! mv "$staged_toolchain" "$TOOLCHAIN_DIR"; then')
verify = bootstrap.index('if ! usable "$TOOLCHAIN_DIR"; then', post)
remove_old = bootstrap.index('rm -rf "$old_toolchain" "$stage_root"', verify)
assert post < verify < remove_old
assert 'mv "$old_toolchain" "$TOOLCHAIN_DIR"' in bootstrap[verify:remove_old]
print("Clang resource ownership and relocated header checks: verified")
