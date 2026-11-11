#!/usr/bin/env python3
"""Build and exercise the C ABI of ui/cocoa-swift.swift on macOS."""

from __future__ import annotations

import os
import pathlib
import platform
import re
import shlex
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SWIFT_SOURCE = ROOT / "ui/cocoa-swift.swift"
HEADER = ROOT / "ui/cocoa-swift.h"


def run(cmd: list[str]) -> str:
    proc = subprocess.run(
        cmd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.stdout


def swift_version(swiftc: str) -> tuple[int, int]:
    out = run([swiftc, "--version"])
    match = re.search(r"(?:Apple )?Swift version\s+(\d+)\.(\d+)", out)
    if not match:
        raise RuntimeError(f"cannot parse Swift version from: {out.strip()}")
    return int(match.group(1)), int(match.group(2))


def deployment_target() -> str:
    value = os.environ.get("MACOSX_DEPLOYMENT_TARGET")
    if value:
        return value
    version = platform.mac_ver()[0]
    if not version:
        return "15.0"
    parts = version.split(".")
    return ".".join(parts[:2])


def host_arch() -> str:
    arch = os.environ.get("WHP_MACOS_ARCH", platform.machine())
    if arch in ("aarch64", "arm64"):
        return "arm64"
    return arch


def main() -> int:
    source = SWIFT_SOURCE.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")

    for token in (
        "@c(qemu_cocoa_swift_interface_version)",
        "@c(qemu_cocoa_swift_pasteboard_change_count)",
        "@c(qemu_cocoa_swift_pasteboard_has_string)",
        "@c(qemu_cocoa_swift_display_refresh_rate)",
        "NSPasteboard.general",
        "CGDisplayCopyDisplayMode",
    ):
        assert token in source, f"missing Swift Cocoa bridge contract: {token}"

    assert "QEMU_COCOA_SWIFT_ABI_VERSION 1" in header
    assert "void *" not in header
    assert "id " not in header

    if sys.platform != "darwin":
        print("SKIP: Cocoa Swift ABI build is macOS-only")
        return 0

    xcrun = "/usr/bin/xcrun"
    swiftc = run([xcrun, "--find", "swiftc"]).strip()
    version = swift_version(swiftc)
    if version < (6, 3):
        print(
            f"SKIP: Swift {version[0]}.{version[1]} lacks the stable @c ABI"
        )
        return 0

    sdk = run([xcrun, "--sdk", "macosx", "--show-sdk-path"]).strip()
    target = f"{host_arch()}-apple-macosx{deployment_target()}"
    cc_env = os.environ.get("CC")
    cc = shlex.split(cc_env) if cc_env else [run([xcrun, "--find", "clang"]).strip()]

    harness = r"""
#include <CoreGraphics/CoreGraphics.h>
#include <assert.h>
#include <stdint.h>
#include "ui/cocoa-swift.h"

int main(void)
{
    double rate;

    assert(qemu_cocoa_swift_interface_version() ==
           QEMU_COCOA_SWIFT_ABI_VERSION);

    rate = qemu_cocoa_swift_display_refresh_rate(CGMainDisplayID());
    assert(rate >= 0.0);

    /*
     * Resolve the AppKit-backed entry points too.  Do not mutate the host
     * pasteboard in CI; querying it is enough to exercise the ABI boundary.
     */
    (void)qemu_cocoa_swift_pasteboard_change_count();
    (void)qemu_cocoa_swift_pasteboard_has_string();
    return 0;
}
"""

    with tempfile.TemporaryDirectory(prefix="qemu-cocoa-swift-") as tmp:
        tmpdir = pathlib.Path(tmp)
        swift_obj = tmpdir / "cocoa-swift.o"
        c_file = tmpdir / "main.c"
        c_obj = tmpdir / "main.o"
        exe = tmpdir / "cocoa-swift-abi"
        c_file.write_text(harness, encoding="utf-8")

        run([
            swiftc,
            "-swift-version", "6",
            "-O",
            "-whole-module-optimization",
            "-parse-as-library",
            "-sdk", sdk,
            "-target", target,
            "-emit-object",
            str(SWIFT_SOURCE),
            "-o", str(swift_obj),
        ])

        run(
            cc
            + [
                "-O2",
                "-isysroot", sdk,
                "-target", target,
                "-I", str(ROOT),
                "-c", str(c_file),
                "-o", str(c_obj),
            ]
        )

        run([
            swiftc,
            "-sdk", sdk,
            "-target", target,
            str(swift_obj),
            str(c_obj),
            "-framework", "AppKit",
            "-framework", "CoreGraphics",
            "-o", str(exe),
        ])

        archs = run(["lipo", "-archs", str(exe)]).split()
        expected_arch = host_arch()
        assert expected_arch in archs, (
            f"Swift Cocoa ABI binary missing {expected_arch}: {archs}"
        )
        run([str(exe)])

    print(
        f"Cocoa Swift ABI passed: Swift {version[0]}.{version[1]} target={target}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
