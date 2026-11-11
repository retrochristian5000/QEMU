#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Evaluate compiler-rt's actual CMake architecture lists on Darwin and Linux."""

from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
architecture_definitions = (
    root / "toolchains/llvm-project/compiler-rt/cmake/Modules/"
    "AllSupportedArchDefs.cmake"
)
if not architecture_definitions.is_file():
    # The lean LLD workflow checks out the pinned gitlink in llvm-project/.
    architecture_definitions = (
        root / "llvm-project/compiler-rt/cmake/Modules/AllSupportedArchDefs.cmake"
    )
if not architecture_definitions.is_file():
    raise SystemExit("missing pinned compiler-rt architecture definitions")

labels = {
    "common": "ALL_SANITIZER_COMMON_SUPPORTED_ARCH",
    "asan": "ALL_ASAN_SUPPORTED_ARCH",
    "asan_abi": "ALL_ASAN_ABI_SUPPORTED_ARCH",
    "ubsan": "ALL_UBSAN_SUPPORTED_ARCH",
    "tsan": "ALL_TSAN_SUPPORTED_ARCH",
    "hwasan": "ALL_HWASAN_SUPPORTED_ARCH",
}

for apple in (True, False):
    with tempfile.TemporaryDirectory(prefix="whp-asan-policy-") as temp:
        script = Path(temp) / "check.cmake"
        lines = [
            f"set(APPLE {'ON' if apple else 'OFF'})",
            f"set(CMAKE_SYSTEM_NAME {'Darwin' if apple else 'Linux'})",
            f'include("{architecture_definitions.as_posix()}")',
        ]
        for label, variable in labels.items():
            lines.append(f'message(STATUS "WHP_{label}=${{{variable}}}")')
        script.write_text("\n".join(lines) + "\n", encoding="utf-8")
        result = subprocess.run(
            ["cmake", "-P", str(script)],
            capture_output=True, text=True, check=False,
        )
        if result.returncode:
            raise SystemExit(
                f"compiler-rt CMake policy evaluation failed ({apple=}):\n"
                + result.stderr
            )
        lists = {}
        for line in (result.stdout + "\n" + result.stderr).splitlines():
            if "WHP_" not in line:
                continue
            pair = line.split("WHP_", 1)[1]
            key, _, values = pair.partition("=")
            lists[key] = set(values.split(";")) if values else set()
        if set(lists) != set(labels):
            raise SystemExit(f"missing policy variables: {lists!r}")
        expected = {"common", "asan", "asan_abi", "ubsan"} if apple else set()
        for label, values in lists.items():
            present = "arm64e" in values
            if present != (label in expected):
                raise SystemExit(
                    f"compiler-rt {'Darwin' if apple else 'Linux'} {label}: "
                    f"ARM64e admission {present}, expected {label in expected}"
                )
        assert "arm64" in lists["asan"] if apple else "aarch64" in lists["asan"]

print("compiler-rt ASan ABI policy: arm64e admitted only to Apple ASan dependencies")
