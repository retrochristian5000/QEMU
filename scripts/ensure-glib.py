#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build the pinned GLib fork as an isolated native QEMU host library."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
MODULES = ("glib-2.0", "gobject-2.0", "gio-2.0", "gio-unix-2.0",
           "gmodule-2.0", "gmodule-export-2.0", "gmodule-no-export-2.0")
INPUTS = ("libffi >= 3.0.0", "libpcre2-8 >= 10.32", "zlib")
PROBE = r"""
#define _GNU_SOURCE
#include <glib.h>
#include <glib-object.h>
#include <gio/gio.h>
#include <gmodule.h>
#include <dlfcn.h>
#include <stdio.h>

static int show_library(void *symbol)
{
    Dl_info info;
    if (!dladdr(symbol, &info) || !info.dli_fname)
        return 1;
    puts(info.dli_fname);
    return 0;
}
int main(void)
{
    if (sizeof(size_t) != GLIB_SIZEOF_SIZE_T ||
        glib_major_version != GLIB_MAJOR_VERSION ||
        glib_minor_version != GLIB_MINOR_VERSION ||
        glib_micro_version != GLIB_MICRO_VERSION ||
        !g_module_supported())
        return 1;
    return show_library((void *)g_get_monotonic_time) ||
           show_library((void *)g_object_get_type) ||
           show_library((void *)g_io_error_quark) ||
           show_library((void *)g_module_supported);
}
"""


def run(command, *, env=None, capture=True):
    result = subprocess.run(
        command, env=env, text=True, check=True,
        stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=subprocess.PIPE if capture else sys.stderr,
    )
    return result.stdout.strip() if capture else ""


def command(value):
    argv = shlex.split(value)
    if not argv:
        raise RuntimeError("empty tool command")
    exe = shutil.which(argv[0])
    if not exe:
        raise RuntimeError(f"tool unavailable: {argv[0]}")
    return [str(Path(exe).absolute()), *argv[1:]]


def pinned_source(parent, relative, git, allow_init):
    target = parent / relative
    entry = run([*git, "-C", str(parent), "ls-tree", "HEAD", "--",
                 relative]).split()
    if len(entry) != 4 or entry[:2] != ["160000", "commit"]:
        raise RuntimeError(f"missing pinned gitlink: {relative}")
    if target.is_symlink():
        raise RuntimeError(f"refusing symlinked source: {target}")
    if not (target / ".git").exists():
        if not allow_init:
            raise RuntimeError(f"initialize pinned source first: {target}")
        run([*git, "-C", str(parent), "submodule", "update", "--init",
             "--depth", "1", "--", relative], capture=False)
    top = Path(run([*git, "-C", str(target), "rev-parse",
                    "--show-toplevel"]))
    if not top.samefile(target):
        raise RuntimeError(f"unexpected Git worktree: {target}")
    actual = run([*git, "-C", str(target), "rev-parse", "HEAD"])
    if actual != entry[2]:
        raise RuntimeError(f"{target} differs from its parent pin; "
                           "preserve the checkout and update the gitlink")
    if run([*git, "-C", str(target), "status", "--porcelain",
            "--untracked-files=normal", "--ignore-submodules=all"]):
        raise RuntimeError(f"uncommitted source changes: {target}")
    return target, actual


def pc_environment(prefix=None):
    env = os.environ.copy()
    if prefix:
        path = str(prefix / "lib/pkgconfig")
        env["PKG_CONFIG_PATH"] = os.pathsep.join(
            [path] + ([env["PKG_CONFIG_PATH"]]
                      if env.get("PKG_CONFIG_PATH") else []))
    return env


def probe(pc, cc, cflags, ldflags, prefix=None):
    env = pc_environment(prefix)
    run([*pc, "--exists", "glib-2.0 >= 2.66.0", *MODULES], env=env)
    if prefix:
        expected = (prefix / "lib/pkgconfig").resolve()
        for module in MODULES:
            actual = Path(run([*pc, "--variable=pcfiledir", module],
                              env=env)).resolve()
            if actual != expected:
                raise RuntimeError(f"{module} selected from {actual}, "
                                   f"expected {expected}")
    flags = shlex.split(run([*pc, "--cflags", "--libs", *MODULES], env=env))
    extra = [f"-Wl,-rpath,{prefix / 'lib'}"] if prefix else []
    if platform.system() == "Linux":
        extra.append("-ldl")
    with tempfile.TemporaryDirectory(prefix="whp-glib-probe-") as directory:
        source = Path(directory) / "probe.c"
        binary = Path(directory) / "probe"
        source.write_text(PROBE, encoding="utf-8")
        run([*cc, *cflags, "-fPIC", str(source), "-o", str(binary),
             *flags, *ldflags, *extra], env=env)
        libs = run([str(binary)], env=env).splitlines()
        if len(libs) != 4:
            raise RuntimeError("GLib loader probe did not identify four libraries")
        if prefix and any(not Path(lib).resolve().is_relative_to(prefix)
                          for lib in libs):
            raise RuntimeError(f"GLib loader selected external libraries: {libs}")


def machine_array(values):
    # Meson machine files require single-quoted strings.
    if any("'" in item or "\n" in item or "\r" in item for item in values):
        raise RuntimeError("unsupported quote/newline in native tool or flag")
    return "[" + ", ".join("'" + item.replace("\\", "\\\\") + "'"
                          for item in values) + "]"


def bootstrap(args):
    if platform.system() not in ("Linux", "Darwin"):
        raise RuntimeError("managed GLib supports native Linux and macOS")
    cc, ar = command(args.cc), command(args.ar)
    pc = command(args.pkg_config)
    cflags = shlex.split(args.cflags) + shlex.split(os.environ.get("CPPFLAGS", ""))
    ldflags = shlex.split(args.ldflags)
    if args.mode == "auto":
        try:
            probe(pc, cc, cflags, ldflags)
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            print("WHP GLib: installed provider failed native probe; "
                  "trying pinned fork", file=sys.stderr)
        else:
            print("WHP GLib: installed provider is usable", file=sys.stderr)
            return None

    meson, ninja = command(args.meson), command(args.ninja)
    git = command(os.environ.get("GIT", "git"))
    source, revision = pinned_source(ROOT, "toolchains/glib", git,
                                     args.allow_source_init)
    _, gvdb = pinned_source(source, "subprojects/gvdb", git,
                            args.allow_source_init)
    run([*pc, "--exists", *INPUTS])
    identity = {
        "schema": 1, "source": str(source), "glib": revision, "gvdb": gvdb,
        "host": [platform.system(), platform.machine()],
        "tools": [(tool, run([*tool, "--version"]))
                  for tool in (cc, ar, pc, meson, ninja)],
        "cflags": cflags, "ldflags": ldflags,
        "environment": {key: os.environ.get(key, "") for key in (
            "SDKROOT", "DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET",
            "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR",
            "CC_LD", "PATH")},
        "inputs": [(package, run([*pc, "--modversion", package]),
                    run([*pc, "--cflags", "--libs", package]),
                    run([*pc, "--variable=pcfiledir", package]))
                   for package in INPUTS],
        "policy": "shared,nodownload,no-tests,no-docs,no-introspection",
    }
    manifest = json.dumps(identity, sort_keys=True, indent=2) + "\n"
    key = hashlib.sha256(manifest.encode()).hexdigest()[:24]
    root = Path(args.build_dir).resolve()
    prefix = root / "deps/glib" / key
    work = root / "bootstrap/glib" / key
    for directory in (prefix, work):
        if directory.resolve() != directory:
            raise RuntimeError(f"refusing symlinked GLib build path: {directory}")
    marker = prefix / ".whp-glib-bootstrap"
    if marker.is_file() and marker.read_text(encoding="utf-8") == manifest:
        probe(pc, cc, cflags, ldflags, prefix)
        print(f"WHP GLib: reusing {revision[:12]} at {prefix}", file=sys.stderr)
        return prefix

    work.parent.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    native = work.parent / (key + ".ini")
    native.write_text(
        "[binaries]\nc = " + machine_array(cc) +
        "\nar = " + machine_array(ar) +
        "\npkg-config = " + machine_array(pc) +
        "\n[built-in options]\nc_args = " + machine_array(cflags) +
        "\nc_link_args = " + machine_array(cflags + ldflags) + "\n",
        encoding="utf-8",
    )
    env = pc_environment()
    for key in ("CC", "AR", "CFLAGS", "CPPFLAGS", "LDFLAGS"):
        env.pop(key, None)
    if len(ninja) != 1:
        raise RuntimeError("Ninja must name one executable")
    env["NINJA"] = ninja[0]
    setup = [*meson, "setup"]
    if (work / "meson-private/coredata.dat").is_file():
        setup.append("--reconfigure")
    print(f"WHP GLib: building {revision[:12]} -> {prefix}", file=sys.stderr)
    run([*setup, str(work), str(source), "--native-file", str(native),
         "--prefix", str(prefix), "--libdir", "lib", "--bindir", "bin",
         "--default-library=shared", "--buildtype=release",
         "--wrap-mode=nodownload", "-Dtests=false", "-Dinstalled_tests=false",
         "-Ddocumentation=false", "-Dintrospection=disabled",
         "-Dman-pages=disabled", "-Dnls=disabled", "-Ddtrace=disabled",
         "-Dsystemtap=disabled", "-Dmultiarch=false"], env=env, capture=False)
    jobs = max(1, int(os.environ.get("JOBS") or min(os.cpu_count() or 1, 8)))
    run([*ninja, "-C", str(work), "-j", str(jobs)], env=env, capture=False)
    run([*meson, "install", "-C", str(work), "--no-rebuild"],
        env=env, capture=False)
    probe(pc, cc, cflags, ldflags, prefix)
    temp_marker = marker.with_suffix(".new")
    temp_marker.write_text(manifest, encoding="utf-8")
    temp_marker.replace(marker)
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", required=True, choices=("auto", "1"))
    parser.add_argument("--allow-source-init", action="store_true")
    for name in ("meson", "ninja", "cc", "ar", "pkg-config"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--cflags", default="")
    parser.add_argument("--ldflags", default="")
    try:
        prefix = bootstrap(parser.parse_args())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as exc:
        print(f"error: WHP GLib bootstrap failed: {exc}", file=sys.stderr)
        if isinstance(exc, subprocess.CalledProcessError) and exc.stderr:
            print(exc.stderr.strip(), file=sys.stderr)
        return 1
    if prefix:
        print(prefix)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
