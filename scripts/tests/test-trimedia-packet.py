#!/usr/bin/env python3
"""Host C regression + optional ASan/UBSan/libFuzzer for TriMedia bytes.

No TriMedia guest compiler or guest sanitizer runtime is required. A
sanitizer request is never silently downgraded to an unsanitized build.
"""
import argparse
import os
import shlex
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PKT = ROOT / "target" / "trimedia"
TESTS = ROOT / "scripts" / "tests"

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--sanitize", choices=("none", "address", "undefined",
                                           "address,undefined"), default="none")
parser.add_argument("--fuzz-runs", type=int, default=0,
                    help="run this many libFuzzer inputs (requires Clang)")
args = parser.parse_args()
if args.fuzz_runs < 0:
    parser.error("--fuzz-runs must be nonnegative")
if args.fuzz_runs and "address" not in args.sanitize:
    parser.error("libFuzzer regression requires --sanitize=address or "
                 "--sanitize=address,undefined")

# Do not import unrelated QEMU CFLAGS/CXXFLAGS/LDFLAGS: host ASan links the
# sanitizer runtime and must not inherit incompatible LTO or target triplets.
cc = shlex.split(os.environ.get("CC", "clang" if args.fuzz_runs else "cc"))
if not cc:
    parser.error("CC must name a host C compiler")
flags = ["-std=c11", "-Wall", "-Wextra", "-Werror", "-UNDEBUG"]
if args.sanitize != "none":
    flags += ["-O1", "-g", "-fno-omit-frame-pointer",
              "-fno-optimize-sibling-calls", "-fno-sanitize-recover=all",
              "-fsanitize=" + args.sanitize]

with tempfile.TemporaryDirectory(prefix="trimedia-packet-") as tmp:
    scratch = Path(tmp)
    shim = scratch / "qemu"
    shim.mkdir()
    (shim / "osdep.h").write_text("#include <string.h>\n", encoding="utf-8")
    flags += ["-I" + str(scratch), "-I" + str(PKT)]
    env = os.environ.copy()
    if "address" in args.sanitize:
        env.setdefault("ASAN_OPTIONS", "halt_on_error=1")
    if "undefined" in args.sanitize:
        env.setdefault("UBSAN_OPTIONS", "halt_on_error=1:print_stacktrace=1")

    def compile_and_run(name, main, extra=(), run_args=()):
        binary = scratch / name
        cmd = cc + flags + list(extra) + [
            str(PKT / "packet.c"), str(TESTS / main), "-o", str(binary)]
        subprocess.run(cmd, check=True, env=env)
        subprocess.run([str(binary), *run_args], check=True, env=env)

    compile_and_run("packet-layout-test", "trimedia-packet-layout-test.c")
    compile_and_run("packet-bounds-test", "trimedia-packet-bounds-test.c")
    if args.fuzz_runs:
        compile_and_run("packet-fuzzer", "trimedia-packet-fuzz.c",
                        extra=("-fsanitize=fuzzer",),
                        run_args=(f"-runs={args.fuzz_runs}", "-max_len=40"))
