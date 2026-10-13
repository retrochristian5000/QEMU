#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify a native Darwin Clang/ASan global-instrumentation link end to end.

Run the *installed* compiler-rt, Clang and selected Mach-O linker together;
do not provide a fake __asan_globals_required or relax undefined symbols.
"""

from __future__ import annotations

import argparse
import os
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


def require_runtime_arch(
    clang: pathlib.Path, runtime: pathlib.Path, arch: str,
) -> None:
    """Reject ABI-compatible-looking libraries without the requested slice.

    macOS can accept arm64 dylibs as dependencies of arm64e code, but that
    fallback is not proof that compiler-rt itself was built with PAC-aware
    arm64e callbacks and metadata. ASan needs its actual runtime tested.
    """
    if arch != "arm64e":
        return
    lipo = clang.with_name("llvm-lipo")
    if not lipo.is_file():
        raise RuntimeError(f"cannot audit ASan arm64e runtime: missing {lipo}")
    result = run([str(lipo), "-archs", str(runtime)])
    if result.returncode or "arm64e" not in result.stdout.split():
        raise RuntimeError(
            "matching Darwin ASan runtime lacks an arm64e slice: " +
            str(runtime) + "\n" + (result.stderr or result.stdout)[-2000:]
        )


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
    require_runtime_arch(clang, runtime, arch)

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


# Explicit ARM64e runtime admission. This is deliberately separate from
# verify(): a Mach-O global section and a successful link do not show that
# dyld can load the matching compiler-rt runtime or that ASan works.
RUNTIME_OK = """
#if defined(WHP_REQUIRE_ARM64E)
#if !defined(__arm64e__) || !defined(__PTRAUTH__)
#error requested ARM64e C++ ABI was not selected
#endif
#endif
__attribute__((noinline)) static int whp_add(int x) { return x + 41; }
int (*volatile whp_callback)(int) = whp_add;
int main() {
    int *data = new int[4];
    data[0] = whp_callback(1);
    int ok = data[0] == 42;
    delete[] data;
    return ok ? 0 : 1;
}
"""

RUNTIME_BAD = """
#if defined(WHP_REQUIRE_ARM64E)
#if !defined(__arm64e__) || !defined(__PTRAUTH__)
#error requested ARM64e C++ ABI was not selected
#endif
#endif
__attribute__((noinline)) static int out_of_bounds(int *data) {
    volatile int *p = data;
    return p[8];
}
int main() {
    int *data = new int[4];
    data[0] = 1;
    return out_of_bounds(data);
}
"""


def verify_runtime(
    clang: pathlib.Path, clangxx: pathlib.Path, arch: str,
    sdkroot: pathlib.Path, deployment: str, use_lld: bool,
) -> None:
    """Require working ASan in a real C++ ARM64e process, not only a link."""
    if arch not in ("arm64", "arm64e", "x86_64"):
        raise RuntimeError(f"unsupported Darwin ASan architecture: {arch}")

    cc_resource = run([str(clang), "--print-resource-dir"])
    cxx_resource = run([str(clangxx), "--print-resource-dir"])
    if (cc_resource.returncode or cxx_resource.returncode or
            not cc_resource.stdout.strip() or not cxx_resource.stdout.strip() or
            pathlib.Path(cc_resource.stdout.strip()).resolve() !=
            pathlib.Path(cxx_resource.stdout.strip()).resolve()):
        raise RuntimeError(
            "Clang and Clang++ do not select the same compiler-rt resource directory"
        )
    runtime = (pathlib.Path(cc_resource.stdout.strip()) / "lib" / "darwin" /
               "libclang_rt.asan_osx_dynamic.dylib")
    if not runtime.is_file():
        raise RuntimeError(f"matching Darwin ASan runtime dylib is missing: {runtime}")
    require_runtime_arch(clang, runtime, arch)

    flags = ["-arch", arch, "-isysroot", str(sdkroot),
             f"-mmacosx-version-min={deployment}",
             "-fsanitize=address", "-O1", "-fno-omit-frame-pointer"]
    if arch == "arm64e":
        flags.append("-DWHP_REQUIRE_ARM64E=1")
    if use_lld:
        flags.append("-fuse-ld=lld")

    with tempfile.TemporaryDirectory(prefix="whp-asan-runtime-") as td:
        root = pathlib.Path(td)
        runtime_env = dict(os.environ)
        # Successful loading must not depend on a user's dyld insertion or
        # fallback search path; the Clang driver owns the ASan runtime link.
        for name in tuple(runtime_env):
            if name.startswith("DYLD_"):
                runtime_env.pop(name)
        # Preserve deterministic validation while collecting enough signal
        # context to diagnose arm64e PAC faults and broken shadow accesses.
        # Symbolization is left offline: this toolchain need not ship a native
        # llvm-symbolizer, and the loaded image/ASLR slide is crash-specific.
        runtime_env["ASAN_OPTIONS"] = (
            "detect_leaks=0:halt_on_error=1:symbolize=0:"
            "dump_registers=1:dump_instruction_bytes=1:"
            "fast_unwind_on_fatal=0"
        )
        for label, source, should_fail in (
            ("healthy", RUNTIME_OK, False),
            ("overflow", RUNTIME_BAD, True),
        ):
            input_file = root / f"{label}.cc"
            output_file = root / label
            input_file.write_text(source, encoding="utf-8")
            command = [str(clangxx), *flags, str(input_file),
                       "-o", str(output_file)]
            linked = run(command)
            if linked.returncode or not output_file.is_file():
                raise RuntimeError(
                    f"ASan C++ {arch} {label} link failed with " +
                    ("Mach-O LLD" if use_lld else "Apple ld") + ":\n" +
                    (linked.stderr or linked.stdout)[-5000:]
                )
            try:
                executed = subprocess.run(
                    [str(output_file)], capture_output=True, text=True,
                    check=False, env=runtime_env, timeout=25,
                )
            except subprocess.TimeoutExpired as exc:
                raise RuntimeError(
                    f"ASan C++ {arch} {label} executable timed out"
                ) from exc
            if not should_fail:
                if executed.returncode:
                    raise RuntimeError(
                        f"ASan C++ {arch} healthy process failed to load/run "
                        f"(exit {executed.returncode}):\n" +
                        (executed.stderr or executed.stdout)[-5000:]
                    )
            elif (executed.returncode == 0 or
                  "AddressSanitizer" not in executed.stderr or
                  "heap-buffer-overflow" not in executed.stderr):
                raise RuntimeError(
                    f"ASan C++ {arch} did not diagnose the intentional "
                    f"heap-buffer-overflow (exit {executed.returncode}):\n" +
                    (executed.stderr or executed.stdout)[-5000:]
                )

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", type=pathlib.Path, required=True)
    parser.add_argument("--readobj", type=pathlib.Path)
    parser.add_argument("--clangxx", type=pathlib.Path)
    parser.add_argument("--arch", choices=("arm64", "arm64e", "x86_64"), required=True)
    parser.add_argument("--sdkroot", type=pathlib.Path, required=True)
    parser.add_argument("--deployment-target", required=True)
    parser.add_argument("--use-lld", action="store_true")
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--execute", action="store_true",
                       help="after the link probe, execute positive/negative ASan C++ tests")
    modes.add_argument("--runtime-only", action="store_true",
                       help="run C++ ASan ABI tests without needing llvm-readobj")
    args = parser.parse_args()
    if not args.runtime_only and args.readobj is None:
        parser.error("--readobj is required unless --runtime-only is selected")
    clangxx = args.clangxx or args.clang.with_name("clang++")
    try:
        if not args.runtime_only:
            verify(
                args.clang, args.readobj, args.arch, args.sdkroot,
                args.deployment_target, args.use_lld,
            )
        if args.execute or args.runtime_only:
            verify_runtime(
                args.clang, clangxx, args.arch, args.sdkroot,
                args.deployment_target, args.use_lld,
            )
    except (OSError, RuntimeError) as exc:
        print(f"error: WHP Darwin ASan global-link check: {exc}", file=sys.stderr)
        return 1
    print("WHP Darwin ASan: " + ("runtime detects memory corruption" if
          (args.execute or args.runtime_only) else
          "instrumented globals linked with matching compiler-rt"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
