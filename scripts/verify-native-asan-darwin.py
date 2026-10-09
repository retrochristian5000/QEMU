#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify a native Darwin Clang/ASan global-instrumentation link end to end.

Run the *installed* compiler-rt, Clang and selected Mach-O linker together;
do not provide a fake __asan_globals_required or relax undefined symbols.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import sys
import tempfile

SOURCE = """\
volatile char whp_asan_global[19] = "WHP-ASan-check";
int main(int argc, char **argv) {
    return whp_asan_global[argc & 31] + (argv != 0);
}
"""


def run(command: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, check=False)


def verify(
    clang: pathlib.Path, readobj: pathlib.Path, arch: str,
    sdkroot: pathlib.Path, deployment: str, use_lld: bool,
) -> None:
    if arch not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(f"unsupported Darwin ASan architecture: {arch}")
    resource = run([str(clang), "--print-resource-dir"])
    if resource.returncode or not resource.stdout.strip():
        raise RuntimeError("selected Clang cannot locate its compiler resource directory")
    runtime = (
        pathlib.Path(resource.stdout.strip()) / "lib" / "darwin" /
        "libclang_rt.asan_osx_dynamic.dylib"
    )
    if not runtime.is_file():
        raise RuntimeError(
            f"matching Clang AddressSanitizer dylib is missing: {runtime}. "
            "Build/install compiler-rt runtimes for the native Clang."
        )

    flags = [
        "-arch", arch, "-isysroot", str(sdkroot),
        f"-mmacosx-version-min={deployment}",
        "-fsanitize=address", "-O1",
    ]
    with tempfile.TemporaryDirectory(prefix="whp-asan-globals-") as td:
        root = pathlib.Path(td)
        source = root / "asan-globals.c"
        obj = root / "asan-globals.o"
        exe = root / "asan-globals"
        source.write_text(SOURCE, encoding="utf-8")
        compile_command = [str(clang), *flags, "-c", str(source), "-o", str(obj)]
        compiled = run(compile_command)
        if compiled.returncode:
            raise RuntimeError(
                "ASan global instrumentation failed during compilation:\n"
                + (compiled.stderr or compiled.stdout)[-5000:]
            )

        sections = run([str(readobj), "--sections", str(obj)])
        if sections.returncode or "__asan_globals" not in sections.stdout:
            raise RuntimeError(
                "ASan compiler output lacks Mach-O __asan_globals metadata. "
                "Check instrumentation flags and clang/LLVM revision."
            )

        # The Clang *driver* must participate in the final link, or it will
        # not add libclang_rt.asan_osx_dynamic from its own resource directory.
        link_command = [str(clang), *flags]
        if use_lld:
            link_command.append("-fuse-ld=lld")
        link_command.extend([str(obj), "-o", str(exe)])
        linked = run(link_command)
        if linked.returncode:
            detail = (linked.stderr or linked.stdout)[-6000:]
            if "__asan_globals_required" in detail:
                comparison = ""
                if use_lld:
                    # One controlled comparison isolates linker support from
                    # Clang's instrumentation and compiler-rt selection.
                    apple_command = [
                        str(clang), *flags, str(obj),
                        "-o", str(root / "asan-globals-apple-ld"),
                    ]
                    apple = run(apple_command)
                    if apple.returncode == 0:
                        comparison = (
                            "Apple ld linked the same ASan object successfully; "
                            "the selected ld64.lld is the likely mismatch.\n"
                        )
                    else:
                        comparison = (
                            "Apple ld also failed on the same ASan object; "
                            "investigate the Clang/compiler-rt/SDK pairing.\n"
                            + (apple.stderr or apple.stdout)[-2000:] + "\n"
                        )
                raise RuntimeError(
                    "Mach-O linker failed on __asan_globals_required while "
                    "linking ASan-instrumented globals. Do not define a dummy "
                    "symbol: verify the selected linker and compiler-rt "
                    "contract.\n" + comparison + detail
                )
            raise RuntimeError(
                "Darwin ASan global instrumentation failed at the final "
                "Clang driver link (selected "
                + ("ld64.lld" if use_lld else "Apple ld")
                + "):\n" + detail
            )
        if not exe.is_file():
            raise RuntimeError("ASan link returned success without an executable")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", type=pathlib.Path, required=True)
    parser.add_argument("--readobj", type=pathlib.Path, required=True)
    parser.add_argument("--arch", choices=("arm64", "arm64e", "x86_64"), required=True)
    parser.add_argument("--sdkroot", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-target", required=True)
    parser.add_argument("--use-lld", action="store_true")
    args = parser.parse_args()
    try:
        verify(
            args.clang, args.readobj, args.arch, args.sdkroot,
            args.deployment_target, args.use_lld,
        )
    except (OSError, RuntimeError) as exc:
        print(f"error: WHP Darwin ASan global-link check: {exc}", file=sys.stderr)
        return 1
    print("WHP Darwin ASan: instrumented globals linked with matching compiler-rt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
