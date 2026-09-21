#!/usr/bin/env python3
"""
Probe Swift as an optional macOS host implementation language.

This is deliberately not part of the QEMU runtime build.  It proves that a
supported Swift toolchain can:
  * target the requested macOS architecture, including arm64e when available;
  * export a Swift 6.3+ @c function with the C calling convention;
  * link that function with C code; and
  * produce competitive optimized code for a self-contained integer kernel.

The benchmark is informational.  Only ABI correctness and result parity are
gating conditions.
"""

from __future__ import annotations

import argparse
import os
import pathlib
import platform
import re
import shlex
import subprocess
import sys
import tempfile


def run(cmd: list[str], *, cwd: pathlib.Path | None = None) -> str:
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return proc.stdout


def swift_version(swiftc: str) -> tuple[int, int]:
    out = run([swiftc, "--version"])
    match = re.search(r"Swift version\s+(\d+)\.(\d+)", out)
    if not match:
        match = re.search(r"Apple Swift version\s+(\d+)\.(\d+)", out)
    if not match:
        raise RuntimeError(f"cannot parse Swift version from: {out.strip()}")
    return int(match.group(1)), int(match.group(2))


def deployment_target() -> str:
    env = os.environ.get("MACOSX_DEPLOYMENT_TARGET")
    if env:
        return env
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
    parser = argparse.ArgumentParser()
    parser.add_argument("--samples", type=int, default=5)
    parser.add_argument("--rounds", type=int, default=10_000_000)
    args = parser.parse_args()

    if sys.platform != "darwin":
        print("SKIP: Swift host probe is macOS-only")
        return 0

    xcrun = "/usr/bin/xcrun"
    swiftc = run([xcrun, "--find", "swiftc"]).strip()
    version = swift_version(swiftc)
    if version < (6, 3):
        print(
            f"SKIP: Swift {version[0]}.{version[1]} lacks the stable @c ABI "
            "used by this probe"
        )
        return 0

    sdk = run([xcrun, "--sdk", "macosx", "--show-sdk-path"]).strip()
    arch = host_arch()
    target = f"{arch}-apple-macosx{deployment_target()}"

    cc_env = os.environ.get("CC")
    if cc_env:
        cc = shlex.split(cc_env)
    else:
        cc = [run([xcrun, "--find", "clang"]).strip()]

    swift_source = r"""
@c(qemu_swift_probe_mix)
public func qemuSwiftProbeMix(_ seed: UInt64, _ rounds: UInt32) -> UInt64 {
    var x = seed
    var i: UInt32 = 0
    while i < rounds {
        x ^= x >> 12
        x ^= x << 25
        x ^= x >> 27
        x &*= 0x2545F4914F6CDD1D
        i &+= 1
    }
    return x
}
"""

    c_source = r"""
#include <inttypes.h>
#include <mach/mach_time.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>

extern uint64_t qemu_swift_probe_mix(uint64_t seed, uint32_t rounds);

__attribute__((noinline))
static uint64_t qemu_c_probe_mix(uint64_t seed, uint32_t rounds)
{
    uint64_t x = seed;
    uint32_t i;

    for (i = 0; i < rounds; i++) {
        x ^= x >> 12;
        x ^= x << 25;
        x ^= x >> 27;
        x *= UINT64_C(0x2545F4914F6CDD1D);
    }
    return x;
}

static double nanos(uint64_t ticks)
{
    mach_timebase_info_data_t info;
    mach_timebase_info(&info);
    return (double)ticks * (double)info.numer / (double)info.denom;
}

int main(int argc, char **argv)
{
    uint32_t rounds = argc > 1 ? (uint32_t)strtoul(argv[1], NULL, 10) : 10000000;
    unsigned samples = argc > 2 ? (unsigned)strtoul(argv[2], NULL, 10) : 5;
    const uint64_t seed = UINT64_C(0x123456789abcdef0);
    double c_best = 1e300;
    double swift_best = 1e300;
    uint64_t c_result = 0;
    uint64_t swift_result = 0;
    unsigned i;

    for (i = 0; i < samples; i++) {
        uint64_t start = mach_absolute_time();
        c_result = qemu_c_probe_mix(seed + i, rounds);
        c_best = __builtin_fmin(c_best, nanos(mach_absolute_time() - start));

        start = mach_absolute_time();
        swift_result = qemu_swift_probe_mix(seed + i, rounds);
        swift_best = __builtin_fmin(swift_best, nanos(mach_absolute_time() - start));

        if (c_result != swift_result) {
            fprintf(stderr,
                    "result mismatch: C=%" PRIx64 " Swift=%" PRIx64 "\n",
                    c_result, swift_result);
            return 2;
        }
    }

    printf("target=%s rounds=%u samples=%u\n", "__TARGET__", rounds, samples);
    printf("C best:     %.0f ns\n", c_best);
    printf("Swift best: %.0f ns\n", swift_best);
    printf("Swift/C:    %.4fx\n", swift_best / c_best);
    return 0;
}
""".replace("__TARGET__", target)

    with tempfile.TemporaryDirectory(prefix="qemu-swift-probe-") as tmp:
        root = pathlib.Path(tmp)
        swift_file = root / "probe.swift"
        c_file = root / "probe.c"
        swift_obj = root / "probe-swift.o"
        c_obj = root / "probe-c.o"
        exe = root / "probe"

        swift_file.write_text(swift_source, encoding="utf-8")
        c_file.write_text(c_source, encoding="utf-8")

        swift_cmd = [
            swiftc,
            "-swift-version", "6",
            "-O",
            "-whole-module-optimization",
            "-parse-as-library",
            "-sdk", sdk,
            "-target", target,
            "-emit-object",
            str(swift_file),
            "-o", str(swift_obj),
        ]
        try:
            run(swift_cmd)
        except subprocess.CalledProcessError as exc:
            print(
                f"SKIP: Swift {version[0]}.{version[1]} cannot build target "
                f"{target}"
            )
            print(exc.stdout)
            return 0

        run(
            cc
            + [
                "-O3",
                "-isysroot", sdk,
                "-target", target,
                "-c", str(c_file),
                "-o", str(c_obj),
            ]
        )

        run(
            [
                swiftc,
                "-sdk", sdk,
                "-target", target,
                str(swift_obj),
                str(c_obj),
                "-o", str(exe),
            ]
        )

        print(f"Swift compiler: {swiftc}")
        print(f"Swift version:  {version[0]}.{version[1]}")
        print(f"Swift target:   {target}")
        print(run([str(exe), str(args.rounds), str(args.samples)]), end="")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
