#!/usr/bin/env python3
"""Run the pinned LLVM libffi fixture without rebuilding the LLVM test suite."""

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "toolchains/llvm-project/compiler-rt/test/tsan/libffi_callbacks.c"
RUNTIME_FIXTURE = FIXTURE.with_name("libffi_argument_race.c")
SCALAR_FIXTURE = FIXTURE.with_name("libffi_scalar_race.c")
PRECISION_FIXTURE = FIXTURE.with_name("libffi_memory_precision.c")
HFA_FIXTURE = FIXTURE.with_name("libffi_aarch64_hfa.c")
TSAN_OPTIONS = (
    "exitcode=66:abort_on_error=0:atexit_sleep_ms=0:"
    "ignore_noninstrumented_modules=0:ignore_interceptors_accesses=0"
)


def run(command, timeout, env=None):
    print("+ " + shlex.join(str(arg) for arg in command), flush=True)
    result = subprocess.run(
        command, env=env, timeout=timeout, text=True, errors="replace",
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False,
    )
    if result.stdout:
        print(result.stdout, end="", flush=True)
    return result


def checked(command, timeout):
    result = run(command, timeout)
    if result.returncode:
        raise RuntimeError(f"command failed with exit status {result.returncode}")
    return result.stdout


def pkg_flags(program, option, timeout):
    result = subprocess.run(
        [program, option, "libffi"], timeout=timeout, text=True,
        capture_output=True, check=False,
    )
    if result.returncode:
        raise RuntimeError(f"libffi pkg-config {option}: {result.stderr.strip()}")
    return shlex.split(result.stdout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True, help="selected native C compiler")
    parser.add_argument("--pkg-config", help="optional selected native pkg-config")
    parser.add_argument("--cflag", action="append", default=[], help="repeat for SDK/ABI/include flags")
    parser.add_argument("--ldflag", action="append", default=[], help="repeat for libffi link flags")
    parser.add_argument("--abi-only", action="store_true", help="run only unsanitized ABI and safe controls")
    parser.add_argument(
        "--runtime-ffi", action="store_true",
        help="require the optional native macOS ffi_call interceptor",
    )
    parser.add_argument("--timeout", type=int, default=60, help="per-command timeout in seconds")
    args = parser.parse_args()
    if args.timeout < 1:
        parser.error("--timeout must be positive")
    if args.runtime_ffi and (args.abi_only or sys.platform != "darwin"):
        parser.error("--runtime-ffi requires a native macOS TSan run")
    if args.runtime_ffi:
        for fixture in (RUNTIME_FIXTURE, SCALAR_FIXTURE, PRECISION_FIXTURE):
            if not fixture.is_file():
                parser.error(f"pinned LLVM runtime fixture missing: {fixture}")
    if not FIXTURE.is_file():
        parser.error(f"pinned LLVM fixture missing: {FIXTURE}; initialize toolchains/llvm-project")
    try:
        cflags = list(args.cflag)
        ldflags = list(args.ldflag)
        if args.pkg_config:
            cflags += pkg_flags(args.pkg_config, "--cflags", args.timeout)
            ldflags += pkg_flags(args.pkg_config, "--libs", args.timeout)
        if not ldflags:
            ldflags = ["-lffi"]
        with tempfile.TemporaryDirectory(prefix="whp-tsan-libffi-") as work:
            base = [args.compiler, "-O1", "-g", "-pthread", *cflags]
            normal = str(Path(work) / "ffi-native")
            sanitized = str(Path(work) / "ffi-tsan")
            checked([*base, str(FIXTURE), *ldflags, "-o", normal], args.timeout)
            for mode in ("abi", "direct-safe", "ffi-safe"):
                checked([normal, mode], args.timeout)
            print("Native libffi ABI and synchronized callbacks: PASS")
            if args.abi_only:
                return 0
            checked([*base, "-fsanitize=thread", str(FIXTURE), *ldflags,
                     "-o", sanitized], args.timeout)
            env = dict(os.environ, TSAN_OPTIONS=TSAN_OPTIONS)
            for mode in ("abi", "direct-safe", "ffi-safe", "direct-race", "ffi-race"):
                result = run([sanitized, mode], args.timeout, env)
                if mode.endswith("-race"):
                    ok = (result.returncode == 66 and
                          "WARNING: ThreadSanitizer: data race" in result.stdout)
                else:
                    ok = (result.returncode == 0 and
                          "WARNING: ThreadSanitizer:" not in result.stdout)
                if not ok:
                    raise RuntimeError(f"TSan {mode} failed: exit {result.returncode}")
                print(f"TSan {mode}: PASS")
            if args.runtime_ffi:
                checked([*base, "-fsanitize=thread", str(RUNTIME_FIXTURE),
                         *ldflags, "-o", sanitized], args.timeout)
                for mode in ("safe", "race"):
                    result = run([sanitized, mode], args.timeout, env)
                    if mode == "race":
                        ok = (result.returncode == 66 and
                              "WARNING: ThreadSanitizer: data race" in result.stdout)
                    else:
                        ok = (result.returncode == 0 and
                              "WARNING: ThreadSanitizer:" not in result.stdout)
                    if not ok:
                        raise RuntimeError(
                            f"TSan ffi_call argument {mode} failed: exit {result.returncode}"
                        )
                    print(f"TSan ffi_call argument {mode}: PASS")
                checked([*base, "-fsanitize=thread", str(SCALAR_FIXTURE),
                         *ldflags, "-o", sanitized], args.timeout)
                for kind in ("narrow", "float", "slot", "result",
                             "small-result", "float-result"):
                    for mode in ("safe", "race"):
                        result = run([sanitized, mode, kind], args.timeout, env)
                        if mode == "race":
                            ok = (result.returncode == 66 and
                                  "WARNING: ThreadSanitizer: data race" in result.stdout)
                        else:
                            ok = (result.returncode == 0 and
                                  "WARNING: ThreadSanitizer:" not in result.stdout)
                        if not ok:
                            raise RuntimeError(
                                f"TSan ffi_call {kind} {mode} failed: exit {result.returncode}"
                            )
                        print(f"TSan ffi_call {kind} {mode}: PASS")
                checked([*base, "-fsanitize=thread", str(PRECISION_FIXTURE),
                         *ldflags, "-o", sanitized], args.timeout)
                result = run([sanitized], args.timeout, env)
                if (result.returncode != 0 or
                        "WARNING: ThreadSanitizer:" in result.stdout):
                    raise RuntimeError(
                        f"TSan ffi_call memory precision failed: exit {result.returncode}"
                    )
                print("TSan ffi_call memory precision: PASS")
                # Use the compiler's actual selected ISA, not the Python
                # process architecture (which may differ under Rosetta).
                macros = checked([args.compiler, *cflags, "-dM", "-E",
                                  "-x", "c", os.devnull], args.timeout)
                is_aarch64 = any(
                    line.split()[:2] == ["#define", "__aarch64__"]
                    for line in macros.splitlines()
                )
                if is_aarch64:
                    if not HFA_FIXTURE.is_file():
                        raise RuntimeError(f"pinned LLVM fixture missing: {HFA_FIXTURE}")
                    checked([*base, "-fsanitize=thread", str(HFA_FIXTURE),
                             *ldflags, "-o", sanitized], args.timeout)
                    for kind in ("arg-reg", "arg-stack", "result-float",
                                 "result-double"):
                        for mode in ("safe", "race", "adjacent"):
                            result = run([sanitized, mode, kind], args.timeout, env)
                            if mode == "race":
                                ok = (result.returncode == 66 and
                                      "WARNING: ThreadSanitizer: data race" in result.stdout)
                            else:
                                ok = (result.returncode == 0 and
                                      "WARNING: ThreadSanitizer:" not in result.stdout)
                            if not ok:
                                raise RuntimeError(
                                    f"TSan AArch64 HFA {kind} {mode} failed: "
                                    f"exit {result.returncode}"
                                )
                            print(f"TSan AArch64 HFA {kind} {mode}: PASS")
                else:
                    print("TSan AArch64 HFA: not applicable to selected compiler ISA")
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"error: libffi TSan validation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
