#!/usr/bin/env python3
"""Build a private TSan-instrumented macOS libc++ application library."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LLVM = ROOT / "toolchains/llvm-project"


def run(args, capture=False, env=None):
    print("+ " + subprocess.list2cmdline([str(arg) for arg in args]), file=sys.stderr)
    return subprocess.run(args, check=True, text=True, env=env,
                          stdout=subprocess.PIPE if capture else None).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--clang", required=True, type=Path)
    parser.add_argument("--clangxx", required=True, type=Path)
    parser.add_argument("--cmake", required=True, type=Path)
    parser.add_argument("--ninja", required=True, type=Path)
    parser.add_argument("--sdk", required=True, type=Path)
    parser.add_argument("--arch", required=True, choices=("arm64", "arm64e", "x86_64"))
    parser.add_argument("--deployment-target", required=True)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--jobs", type=int, default=2)
    args = parser.parse_args()
    if sys.platform != "darwin":
        parser.error("this private libc++ profile requires a native macOS host")
    if args.jobs < 1:
        parser.error("--jobs must be positive")
    if not all(part.isdecimal() for part in args.deployment_target.split(".")):
        parser.error("--deployment-target must be a numeric macOS version")
    for name in ("clang", "clangxx", "cmake", "ninja"):
        path = getattr(args, name)
        if not path.is_absolute() or not path.is_file() or not os.access(path, os.X_OK):
            parser.error(f"--{name} must name an absolute executable path")
    if not args.sdk.is_absolute() or not (args.sdk / "SDKSettings.json").is_file():
        parser.error("--sdk must name a macOS SDK directory")
    if not all((LLVM / part / "CMakeLists.txt").is_file()
               for part in ("runtimes", "libcxx", "libcxxabi")):
        parser.error("initialize the pinned LLVM submodule before building libc++")

    if args.work_dir.is_symlink():
        parser.error("--work-dir must not be a symbolic link")
    work = args.work_dir.resolve()
    if work == ROOT or work in ROOT.parents or work == LLVM or LLVM in work.parents:
        parser.error("--work-dir must be separate from the repository and LLVM sources")
    prefix = work / "install"
    build = work / "build"
    marker = work / ".whp-tsan-libcxx.json"
    try:
        # Only reuse a directory owned by this profile; never install into a
        # pre-existing unrelated prefix, or follow an output-directory symlink.
        if work.exists() and not marker.is_file() and any(work.iterdir()):
            raise RuntimeError("work directory is nonempty and not a libc++ profile")
        if any(p.is_symlink() for p in (prefix, build, marker)):
            raise RuntimeError("profile output paths must not be symbolic links")
        identity = {
            "schema": 1,
            "llvm": run(["git", "-C", str(LLVM), "rev-parse", "HEAD"], True).strip(),
            "clang": str(args.clang), "clangxx": str(args.clangxx),
            "cc_version": run([str(args.clang), "--version"], True),
            "cxx_version": run([str(args.clangxx), "--version"], True),
            "cmake": str(args.cmake), "ninja": str(args.ninja),
            "sdk": str(args.sdk.resolve()),
            "sdk_settings": json.loads((args.sdk / "SDKSettings.json").read_text()),
            "arch": args.arch,
            "deployment_target": args.deployment_target,
        }
        if not str(identity["sdk_settings"].get("CanonicalName", "")).startswith("macosx"):
            raise RuntimeError("selected SDK is not macOS")
        pin = run(["git", "-C", str(ROOT), "rev-parse", "HEAD:toolchains/llvm-project"], True).strip()
        if identity["llvm"] != pin:
            raise RuntimeError("LLVM checkout does not match the QEMU gitlink")
        if marker.exists() and json.loads(marker.read_text()) != identity:
            raise RuntimeError("profile identity changed; select a separate work directory")
        work.mkdir(mode=0o700, parents=True, exist_ok=True)
        if not marker.exists():
            with marker.open("x", encoding="utf-8") as stream:
                json.dump(identity, stream, indent=2)
                stream.write("\n")
        abi = ["-arch", args.arch, "-isysroot", str(args.sdk),
               f"-mmacosx-version-min={args.deployment_target}"]
        # Require the selected compiler and sanitizer runtime to work before
        # spending time on the library build. Never substitute another ABI.
        probe = work / "compiler-probe.cpp"
        probe.write_text("int main() { return 0; }\n", encoding="utf-8")
        probe_bin = work / "compiler-probe"
        run([str(args.clangxx), *abi, "-fsanitize=thread", str(probe), "-o", str(probe_bin)])
        if run(["/usr/bin/lipo", "-archs", str(probe_bin)], True).split() != [args.arch]:
            raise RuntimeError("compiler probe does not match selected macOS architecture")
        env = dict(os.environ, TSAN_OPTIONS="exitcode=66:report_atomic_races=1")
        run([str(probe_bin)], env=env)
        run([str(args.cmake), "-S", str(LLVM / "runtimes"), "-B", str(build),
             "-G", "Ninja", f"-DCMAKE_MAKE_PROGRAM={args.ninja}",
             f"-DCMAKE_C_COMPILER={args.clang}", f"-DCMAKE_CXX_COMPILER={args.clangxx}",
             f"-DCMAKE_OSX_SYSROOT={args.sdk}", f"-DCMAKE_OSX_ARCHITECTURES={args.arch}",
             f"-DCMAKE_OSX_DEPLOYMENT_TARGET={args.deployment_target}",
             f"-DCMAKE_INSTALL_PREFIX={prefix}", "-DCMAKE_BUILD_TYPE=RelWithDebInfo",
             "-DCMAKE_TRY_COMPILE_TARGET_TYPE=STATIC_LIBRARY",
             "-DLLVM_ENABLE_RUNTIMES=libcxx;libcxxabi", "-DLLVM_USE_SANITIZER=Thread",
             "-DLLVM_INCLUDE_TESTS=OFF", "-DLLVM_INCLUDE_DOCS=OFF",
             "-DLIBCXX_INCLUDE_TESTS=OFF", "-DLIBCXX_INCLUDE_BENCHMARKS=OFF",
             "-DLIBCXX_ENABLE_SHARED=OFF", "-DLIBCXX_ENABLE_STATIC=ON",
             "-DLIBCXX_HERMETIC_STATIC_LIBRARY=ON", "-DLIBCXX_CXX_ABI=libcxxabi",
             "-DLIBCXX_ENABLE_STATIC_ABI_LIBRARY=ON", "-DLIBCXX_INSTALL_LIBRARY_DIR=lib",
             "-DLIBCXXABI_INCLUDE_TESTS=OFF", "-DLIBCXXABI_ENABLE_SHARED=OFF",
             "-DLIBCXXABI_ENABLE_STATIC=ON", "-DLIBCXXABI_HERMETIC_STATIC_LIBRARY=ON",
             "-DLIBCXXABI_USE_LLVM_UNWINDER=OFF", "-DLIBCXXABI_INSTALL_LIBRARY_DIR=lib"])
        run([str(args.cmake), "--build", str(build), "--parallel", str(args.jobs)])
        run([str(args.cmake), "--install", str(build)])
        archive = prefix / "lib/libc++.a"
        headers = prefix / "include/c++/v1"
        if not archive.is_file() or not (headers / "memory").is_file():
            raise RuntimeError("private libc++ archive or headers were not installed")
        symbols = run(["/usr/bin/nm", "-u", str(archive)], True)
        if "___tsan_read" not in symbols or "___tsan_atomic" not in symbols:
            raise RuntimeError("libc++ archive lacks TSan read or atomic instrumentation")
        if run(["/usr/bin/lipo", "-archs", str(archive)], True).split() != [args.arch]:
            raise RuntimeError("libc++ archive does not match selected macOS architecture")
        app = work / "libcxx-probe.cpp"
        app.write_text(
            "#include <memory>\n#include <string>\n#include <thread>\n"
            "int main() { auto owner = std::make_shared<std::string>(128, 'x');\n"
            "  std::weak_ptr<std::string> weak(owner); int result = 1;\n"
            "  std::thread t([&] { auto value = weak.lock();\n"
            "    if (value && *value == std::string(128, 'x')) result = 0; });\n"
            "  t.join(); return result; }\n", encoding="utf-8")
        app_bin = work / "libcxx-probe"
        run([str(args.clangxx), *abi, "-std=c++17", "-fsanitize=thread",
             "-nostdinc++", "-isystem", str(headers), "-nostdlib++", str(app),
             str(archive), "-o", str(app_bin)])
        dependencies = run(["/usr/bin/otool", "-L", str(app_bin)], True)
        if any("libc++." in line or "libc++abi." in line
               for line in dependencies.splitlines()[1:]):
            raise RuntimeError("application probe linked a second dynamic C++ library")
        run([str(app_bin)], env=env)
        print(prefix)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as exc:
        print(f"error: private TSan libc++: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
