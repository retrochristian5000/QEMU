#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify native LLVM menu settings reach bootstrap ABI and CMake consumers.

Hermetic Linux/macOS policy probes: no LLVM build or macOS SDK required.
"""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "scripts/whp-config/config.py"
BOOTSTRAP = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(
    encoding="utf-8"
)
BUILD = (ROOT / "build.sh").read_text(encoding="utf-8")

MENU_KEYS = (
    "BOOTSTRAP_NATIVE_LLVM",
    "NATIVE_LLVM_CXX_STANDARD",
    "NATIVE_LLVM_PCH",
    "NATIVE_LLVM_MACOS_ARCH",
    "NATIVE_LLVM_ENABLE_LLDB",
    "NATIVE_LLVM_VALIDATE_ASAN",
    "NATIVE_LLVM_ASAN_AUTO_DEBUG",
    "NATIVE_LLVM_LINK_JOBS",
    "NATIVE_LLVM_COMPILE_JOBS",
    "NATIVE_LLVM_TABLEGEN_JOBS",
)

# Use the saved schema through the actual --shell interface, not a synthetic
# copy of Python option-to-environment conversions.
with tempfile.TemporaryDirectory(prefix="whp-native-llvm-menu-") as td:
    config_path = Path(td) / ".whpconfig"
    config_path.write_text(
        "WHP_CONFIG_VERSION=3\n"
        "BOOTSTRAP_NATIVE_LLVM=y\n"
        "NATIVE_LLVM_CXX_STANDARD=26\n"
        "NATIVE_LLVM_PCH=y\n"
        "NATIVE_LLVM_MACOS_ARCH=arm64e\n"
        "NATIVE_LLVM_ENABLE_LLDB=y\n"
        "NATIVE_LLVM_VALIDATE_ASAN=y\n"
        "NATIVE_LLVM_ASAN_AUTO_DEBUG=y\n"
        "NATIVE_LLVM_LINK_JOBS=3\n"
        "NATIVE_LLVM_COMPILE_JOBS=4\n"
        "NATIVE_LLVM_TABLEGEN_JOBS=2\n",
        encoding="utf-8",
    )
    clean_env = os.environ.copy()
    for key in MENU_KEYS:
        clean_env.pop(key, None)

    def exported(overrides=None):
        env = dict(clean_env)
        env.update(overrides or {})
        output = subprocess.run(
            ["python3", str(CONFIG), "--shell", str(config_path)],
            env=env, capture_output=True, text=True, check=True,
        ).stdout
        # POSIX shell can source the same assignments build.sh evaluates.
        values = subprocess.run(
            ["sh", "-c", output + "\n" +
             'for key in ' + " ".join(MENU_KEYS) + '; do\n' +
             '  eval "value=\\${$key-}"\n' +
             '  printf "%s=%s\\n" "$key" "$value"\n' +
             'done\n'],
            env=env, capture_output=True, text=True, check=True,
        ).stdout.splitlines()
        return dict(line.split("=", 1) for line in values), output

    selected, shell_text = exported()
    wanted = {
        "BOOTSTRAP_NATIVE_LLVM": "1",
        "NATIVE_LLVM_CXX_STANDARD": "26",
        "NATIVE_LLVM_PCH": "1",
        "NATIVE_LLVM_MACOS_ARCH": "arm64e",
        "NATIVE_LLVM_ENABLE_LLDB": "1",
        "NATIVE_LLVM_VALIDATE_ASAN": "1",
        "NATIVE_LLVM_ASAN_AUTO_DEBUG": "1",
        "NATIVE_LLVM_LINK_JOBS": "3",
        "NATIVE_LLVM_COMPILE_JOBS": "4",
        "NATIVE_LLVM_TABLEGEN_JOBS": "2",
    }
    assert selected == wanted, (selected, shell_text)

    # Explicit environment overrides win over saved menu choices, including
    # auto: bootstrap must interpret auto the same way as an omitted value.
    selected, shell_text = exported({
        "NATIVE_LLVM_MACOS_ARCH": "arm64",
        "NATIVE_LLVM_LINK_JOBS": "auto",
        "NATIVE_LLVM_COMPILE_JOBS": "auto",
        "NATIVE_LLVM_TABLEGEN_JOBS": "auto",
    })
    assert selected["NATIVE_LLVM_MACOS_ARCH"] == "arm64"
    for key in (
        "NATIVE_LLVM_MACOS_ARCH", "NATIVE_LLVM_LINK_JOBS",
        "NATIVE_LLVM_COMPILE_JOBS", "NATIVE_LLVM_TABLEGEN_JOBS",
    ):
        assert f"{key}=" not in shell_text, (key, shell_text)
    for key in ("NATIVE_LLVM_LINK_JOBS", "NATIVE_LLVM_COMPILE_JOBS",
                "NATIVE_LLVM_TABLEGEN_JOBS"):
        assert selected[key] == "auto"

# Test the real job policy; keep the Bash extraction markers narrow so this
# remains an executable contract rather than a parallel implementation.
link_policy = BOOTSTRAP.split(
    "# WHP_NATIVE_LLVM_MENU_LINK_JOBS_BEGIN\n", 1
)[1].split("# WHP_NATIVE_LLVM_MENU_LINK_JOBS_END", 1)[0]
pool_policy = BOOTSTRAP.split(
    "# Cap expensive LLVM compile and TableGen work independently of -j and links.\n", 1
)[1].split('host_id="$host_tag-$host_platform"', 1)[0]

def run_jobs(host, overrides):
    env = os.environ.copy()
    for key in MENU_KEYS:
        env.pop(key, None)
    env.update(overrides)
    env["WHP_HOST_OS"] = host
    script = (
        "set -euo pipefail\n"
        'host_os="$WHP_HOST_OS"\n'
        'LLVM_LINK_JOBS="${NATIVE_LLVM_LINK_JOBS:-2}"\n'
        'LLVM_COMPILE_JOBS="${NATIVE_LLVM_COMPILE_JOBS-}"\n'
        'LLVM_TABLEGEN_JOBS="${NATIVE_LLVM_TABLEGEN_JOBS-}"\n'
        + link_policy + pool_policy +
        'printf "%s|%s|%s\\n" "$LLVM_LINK_JOBS" '
        '"${LLVM_COMPILE_JOBS:-unlimited}" '
        '"${LLVM_TABLEGEN_JOBS:-unlimited}"\n'
    )
    return subprocess.run(
        ["bash", "-c", script], env=env, capture_output=True, text=True
    )

for host, overrides, expected in (
    ("macos", {}, "2|2|1"),
    ("macos", {
        "NATIVE_LLVM_LINK_JOBS": "auto",
        "NATIVE_LLVM_COMPILE_JOBS": "auto",
        "NATIVE_LLVM_TABLEGEN_JOBS": "auto",
    }, "2|2|1"),
    ("linux", {
        "NATIVE_LLVM_LINK_JOBS": "auto",
        "NATIVE_LLVM_COMPILE_JOBS": "auto",
        "NATIVE_LLVM_TABLEGEN_JOBS": "auto",
    }, "2|unlimited|unlimited"),
    ("macos", {
        "NATIVE_LLVM_LINK_JOBS": "3",
        "NATIVE_LLVM_COMPILE_JOBS": "4",
        "NATIVE_LLVM_TABLEGEN_JOBS": "2",
    }, "3|4|2"),
    ("macos", {
        "NATIVE_LLVM_LINK_JOBS": "1",
        "NATIVE_LLVM_COMPILE_JOBS": "0",
        "NATIVE_LLVM_TABLEGEN_JOBS": "0",
    }, "1|unlimited|unlimited"),
):
    output = run_jobs(host, overrides)
    assert output.returncode == 0 and output.stdout.strip() == expected, (
        host, overrides, output.stdout, output.stderr,
    )
for bad in ("0", "no", "-2"):
    result = run_jobs("macos", {"NATIVE_LLVM_LINK_JOBS": bad})
    assert result.returncode != 0 and "NATIVE_LLVM_LINK_JOBS" in result.stderr
for key in ("NATIVE_LLVM_COMPILE_JOBS", "NATIVE_LLVM_TABLEGEN_JOBS"):
    result = run_jobs("linux", {key: "invalid"})
    assert result.returncode != 0 and key in result.stderr

# A non-macOS host must not silently accept an explicit Apple-only choice.
platform_guard = BOOTSTRAP.split(
    "# WHP_NATIVE_LLVM_PLATFORM_MENU_GUARD_BEGIN\n", 1
)[1].split("# WHP_NATIVE_LLVM_PLATFORM_MENU_GUARD_END", 1)[0]
def run_platform_guard(host, arch="auto", asan="auto"):
    return subprocess.run(
        ["bash", "-c", "set -euo pipefail\n" +
         f"host_os={host}\n" +
         f"NATIVE_LLVM_MACOS_ARCH={arch}\n" +
         f"native_llvm_asan_setting={asan}\n" +
         platform_guard], capture_output=True, text=True,
    )
assert run_platform_guard("linux").returncode == 0
assert run_platform_guard("linux", asan="auto").returncode == 0
assert run_platform_guard("macos", arch="arm64e", asan="1").returncode == 0
for arch, asan, expected in (
    ("arm64e", "auto", "NATIVE_LLVM_MACOS_ARCH"),
    ("auto", "1", "NATIVE_LLVM_VALIDATE_ASAN"),
):
    result = run_platform_guard("linux", arch, asan)
    assert result.returncode != 0 and expected in result.stderr, result.stderr

# Native LLVM and QEMU host executable ABI settings are independent.
assert 'NATIVE_LLVM_DIR=$("$WHP_BUILD_BASH" --noprofile --norc' in BUILD
assert "WHP ABI selections: LLVM host=%s; QEMU host=%s" in BUILD
assert 'requested_macos_arch="${NATIVE_LLVM_MACOS_ARCH:-auto}"' in BOOTSTRAP
assert '"-DCMAKE_OSX_ARCHITECTURES=$darwin_cmake_arch"' in BOOTSTRAP
assert '"-DLLVM_HOST_TRIPLE=$llvm_host_triple"' in BOOTSTRAP
assert '"-DLLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple"' in BOOTSTRAP
assert "MACOS_BOOTSTRAP_ARCH=$darwin_cmake_arch" in BOOTSTRAP
assert "LLVM_HOST_TRIPLE=$llvm_host_triple" in BOOTSTRAP
assert "LLVM_DEFAULT_TARGET_TRIPLE=$llvm_default_target_triple" in BOOTSTRAP

print("native LLVM menuconfig ABI and pool handoff: passed")
