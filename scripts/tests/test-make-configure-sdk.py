#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the native SDK handoff before GNU Make configures itself."""

from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
MODULE = ROOT / "scripts" / "ensure-make.py"


def main() -> int:
    spec = importlib.util.spec_from_file_location("whp_ensure_make", MODULE)
    if spec is None or spec.loader is None:
        raise SystemExit("cannot load GNU Make bootstrap")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    cc = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if not cc:
        raise SystemExit("a native C compiler is required for the Make SDK test")

    with tempfile.TemporaryDirectory(prefix="whp-make-sdk-test-") as root:
        tmp = pathlib.Path(root)
        developer = tmp / "Developer"
        sdk = developer / "SDKs" / "MacOSX15.0.sdk"
        fakebin = tmp / "bin"
        sdk.mkdir(parents=True)
        fakebin.mkdir()
        xcrun = fakebin / "xcrun"
        xcrun.write_text(
            '#!/bin/sh\n'
            'if [ "$1:$2:$3" = "--sdk:macosx:--show-sdk-path" ]; then\n'
            '  printf "%s\\n" "$TEST_MAKE_SDK"\n'
            'else exit 1; fi\n',
            encoding="utf-8",
        )
        xcrun.chmod(0o755)

        env = {
            "DEVELOPER_DIR": str(developer),
            "SDKROOT": str(sdk),
            "TEST_MAKE_SDK": str(sdk),
            "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
        }
        with mock.patch.object(helper.platform, "system", return_value="Darwin"):
            with mock.patch.dict(os.environ, env):
                assert helper.select_macos_sdkroot() == str(sdk)

                # No inherited SDKROOT: discover one through the same
                # selected Apple developer root, not an unrelated SDK.
                os.environ["SDKROOT"] = ""
                assert helper.select_macos_sdkroot() == str(sdk)

                # Explicit iOS SDKs and foreign developer roots fail closed.
                foreign = tmp / "unselected" / "MacOSX15.0.sdk"
                foreign.mkdir(parents=True)
                os.environ["SDKROOT"] = str(foreign)
                try:
                    helper.select_macos_sdkroot()
                except RuntimeError as exc:
                    assert "outside the selected Apple developer directory" in str(exc)
                else:
                    raise AssertionError("accepted an unselected Apple SDK")

                ios = developer / "SDKs" / "iPhoneOS18.0.sdk"
                ios.mkdir(parents=True)
                os.environ["SDKROOT"] = str(ios)
                try:
                    helper.select_macos_sdkroot()
                except RuntimeError as exc:
                    assert "not a native macOS SDK" in str(exc)
                else:
                    raise AssertionError("accepted a foreign-platform Apple SDK")

        with mock.patch.object(helper.platform, "system", return_value="Linux"):
            assert helper.select_macos_sdkroot() == ""

        # Exercise a native link+run with the environment that configure
        # receives, then prove a failed compiler is not silently accepted.
        native_env = os.environ.copy()
        native_env["SDKROOT"] = str(sdk)
        helper.validate_configure_compiler(cc, native_env, tmp)
        invalid_cc = shutil.which("false")
        if invalid_cc:
            try:
                helper.validate_configure_compiler(invalid_cc, native_env, tmp)
            except RuntimeError as exc:
                assert "configure host compiler cannot link/run" in str(exc)
                assert "SDKROOT=" in str(exc)
            else:
                raise AssertionError("accepted a compiler that cannot link")

    print("GNU Make SDK selection and configure compiler preflight: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
