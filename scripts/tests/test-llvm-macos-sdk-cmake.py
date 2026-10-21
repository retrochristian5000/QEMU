#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the actual LLVM pre-project macOS SDK resolver without an Apple SDK."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile


ROOT = Path(__file__).resolve().parents[2]
LLVM_CMAKE = ROOT / "toolchains/llvm-project/llvm/CMakeLists.txt"


def main() -> int:
    # The fixture uses a POSIX xcrun wrapper and SDK symlinks. Native Windows
    # LLVM configurations are separate and must not require these fixtures.
    if os.name == "nt":
        print("LLVM macOS SDK CMake tests: skipped on Windows")
        return 0
    if not LLVM_CMAKE.is_file():
        print("LLVM macOS SDK CMake tests: skipped (LLVM submodule absent)")
        return 0
    if shutil.which("cmake") is None:
        raise SystemExit("error: CMake is required to test SDK resolution")

    source = LLVM_CMAKE.read_text(encoding="utf-8")
    start = source.index("# Resolve the native Apple SDK before project()")
    end = source.index("\nproject(LLVM", start)
    selection = source[start:end]
    if "set(CMAKE_OSX_SYSROOT" not in selection:
        raise AssertionError("LLVM CMake no longer pins the selected SDK")

    with tempfile.TemporaryDirectory(prefix="whp-cmake-sdk-") as tmp:
        work = Path(tmp)
        bin_dir = work / "bin"
        bin_dir.mkdir()
        active = work / "MacOSX26.0.sdk"
        custom = work / "MacOSX15.0.sdk"
        iphone = work / "iPhoneOS18.0.sdk"
        simulator = work / "iPhoneSimulator18.0.sdk"
        invalid = work / "MacOSX10.0.sdk"
        for sdk in (active, custom, iphone, simulator, invalid):
            sdk.mkdir()
            if sdk != invalid:
                header = sdk / "usr/include/TargetConditionals.h"
                header.parent.mkdir(parents=True)
                header.write_text("/* synthetic SDK for selection only */\n",
                                  encoding="utf-8")
        alias = work / "selected-macos.sdk"
        alias.symlink_to(custom, target_is_directory=True)
        fake_xcrun = bin_dir / "xcrun"
        fake_xcrun.write_text(
            '#!/bin/sh\n'
            'test "$1" = "--sdk" && test "$2" = "macosx" && '
            'test "$3" = "--show-sdk-path" || exit 23\n'
            'printf "%s\\n" "$FAKE_MACOSX_SDK"\n',
            encoding="utf-8",
        )
        fake_xcrun.chmod(0o755)
        script = work / "select-sdk.cmake"
        script.write_text(
            'set(CMAKE_HOST_APPLE TRUE)\n'
            'set(CMAKE_SYSTEM_NAME "Darwin")\n'
            + selection +
            '\nmessage(STATUS "WHP_RESULT_SDK=${CMAKE_OSX_SYSROOT}")\n'
            'message(STATUS "WHP_RESULT_ENV=$ENV{SDKROOT}")\n',
            encoding="utf-8",
        )

        def invoke(*, requested=None, environment=None, source_file=script):
            env = os.environ.copy()
            env.pop("SDKROOT", None)
            env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")
            env["FAKE_MACOSX_SDK"] = str(active)
            if environment is not None:
                env["SDKROOT"] = str(environment)
            args = ["cmake", "-DLLVM_MACOS_HOST_SDK_RESOLVE=ON"]
            if requested is not None:
                args.append("-DCMAKE_OSX_SYSROOT=" + str(requested))
            args.extend(["-P", str(source_file)])
            return subprocess.run(args, env=env, capture_output=True,
                                  text=True, check=False)

        def accept(label, expected, **kwargs):
            result = invoke(**kwargs)
            output = result.stdout + result.stderr
            assert result.returncode == 0, (label, output)
            assert f"WHP_RESULT_SDK={expected}" in output, (label, output)
            assert f"WHP_RESULT_ENV={expected}" in output, (label, output)

        def reject(label, marker, **kwargs):
            result = invoke(**kwargs)
            output = result.stdout + result.stderr
            assert result.returncode != 0, (label, output)
            assert marker in output, (label, output)

        accept("automatic macOS SDK", active)
        accept("SDKROOT override", custom, environment=custom)
        accept("CMake override beats inherited iOS", custom,
               requested=custom, environment=iphone)
        accept("explicit macosx resolves via xcrun", active,
               requested="macosx", environment=simulator)
        accept("symlinks resolve to actual SDK", custom, requested=alias)
        reject("iPhoneOS SDK rejected", "requires MacOSX.sdk",
               environment=iphone)
        reject("simulator SDK rejected", "requires MacOSX.sdk",
               requested=simulator)
        reject("missing SDK headers rejected", "lacks TargetConditionals.h",
               requested=invalid)
        reject("unsupported symbolic name", "absolute path or 'macosx'",
               requested="iphoneos")
        reject("missing SDK directory", "SDK directory is missing",
               requested=work / "missing" / "MacOSX.sdk")
        cross = work / "cross-build.cmake"
        cross.write_text(
            'set(CMAKE_HOST_APPLE TRUE)\n'
            'set(CMAKE_SYSTEM_NAME "iOS")\n'
            + selection, encoding="utf-8"
        )
        reject("Apple cross-target must not select host SDK",
               "native macOS LLVM host tools only", source_file=cross)

    print("LLVM macOS CMake SDK selection: 11 cases passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
