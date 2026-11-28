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
# Keep the optional host-tool profile and its cache identity in one place.
# Do not disable GIO filesystem/security backends or public core APIs.
MESON_PROFILE = (
    "--default-library=shared", "--buildtype=release",
    "-Dtests=false", "-Dinstalled_tests=false", "-Ddocumentation=false",
    "-Dintrospection=disabled", "-Dman-pages=disabled", "-Dnls=disabled",
    "-Ddtrace=disabled", "-Dsystemtap=disabled", "-Dmultiarch=false",
    "-Dsysprof=disabled", "-Dlibelf=disabled", "-Doss_fuzz=disabled",
)
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


def tool_identity(tool):
    # Apple's cctools ar has no portable --version option. The executable
    # identity still distinguishes updates without rejecting Apple ar.
    executable = Path(tool[0]).resolve()
    stat = executable.stat()
    try:
        version = run([*tool, "--version"])
    except subprocess.CalledProcessError:
        version = ""
    return {
        "argv": tool, "path": str(executable), "size": stat.st_size,
        "mtime_ns": stat.st_mtime_ns, "version": version,
    }


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


def dependency_inputs(pc):
    """Fingerprint available host inputs; let Meson resolve missing ones."""
    inputs = []
    for package in INPUTS:
        try:
            run([*pc, "--exists", package])
        except subprocess.CalledProcessError as exc:
            if exc.returncode != 1:
                raise
            # A missing .pc provider is not fatal: the pinned wrap may be
            # available from the source/cache, even in offline mode.
            inputs.append({"requirement": package, "pkg_config": "unavailable"})
            print(f"WHP GLib: {package} unavailable via pkg-config; "
                  "deferring dependency resolution to Meson", file=sys.stderr)
            continue
        inputs.append({
            "requirement": package,
            "pkg_config": "available",
            "version": run([*pc, "--modversion", package]),
            "flags": run([*pc, "--cflags", "--libs", package]),
            "pcfiledir": run([*pc, "--variable=pcfiledir", package]),
        })
    return inputs


def wrap_mode(allow_download):
    return "default" if allow_download else "nodownload"


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
    identity = {
        "schema": 3, "source": str(source), "glib": revision, "gvdb": gvdb,
        "host": [platform.system(), platform.machine()],
        "tools": [tool_identity(tool)
                  for tool in (cc, ar, pc, meson, ninja)],
        "cflags": cflags, "ldflags": ldflags,
        "environment": {key: os.environ.get(key, "") for key in (
            "SDKROOT", "DEVELOPER_DIR", "MACOSX_DEPLOYMENT_TARGET",
            "PKG_CONFIG_PATH", "PKG_CONFIG_LIBDIR", "PKG_CONFIG_SYSROOT_DIR",
            "CC_LD", "PATH")},
        "inputs": dependency_inputs(pc),
        # Download permission is not a library ABI input. Online and offline
        # runs can reuse an identical validated installation.
        "profile": list(MESON_PROFILE),
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
    if marker.is_symlink():
        raise RuntimeError(f"refusing symlinked GLib marker: {marker}")
    if marker.is_file() and marker.read_text(encoding="utf-8") == manifest:
        try:
            probe(pc, cc, cflags, ldflags, prefix)
        except (OSError, RuntimeError, subprocess.CalledProcessError):
            print("WHP GLib: cached installation failed validation; "
                  "repairing the existing build", file=sys.stderr)
            marker.unlink()
        else:
            print(f"WHP GLib: reusing {revision[:12]} at {prefix}", file=sys.stderr)
            return prefix

    work.parent.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(parents=True, exist_ok=True)
    native = work.parent / (key + ".ini")
    if native.is_symlink():
        raise RuntimeError(f"refusing symlinked native file: {native}")
    native.write_text(
        "[binaries]\nc = " + machine_array(cc) +
        "\nar = " + machine_array(ar) +
        "\npkg-config = " + machine_array(pc) +
        "\n[built-in options]\nc_args = " + machine_array(cflags) +
        "\nc_link_args = " + machine_array(cflags + ldflags) + "\n",
        encoding="utf-8",
    )
    env = pc_environment()
    for key in ("CC", "AR", "CFLAGS", "CPPFLAGS", "LDFLAGS", "DESTDIR"):
        env.pop(key, None)
    if len(ninja) != 1:
        raise RuntimeError("Ninja must name one executable")
    env["NINJA"] = ninja[0]
    setup = [*meson, "setup"]
    if (work / "meson-private/coredata.dat").is_file():
        setup.append("--reconfigure")
    mode = wrap_mode(args.allow_download)
    print(f"WHP GLib: building {revision[:12]} -> {prefix} "
          f"(wrap-mode={mode})", file=sys.stderr)
    run([*setup, str(work), str(source), "--native-file", str(native),
         "--prefix", str(prefix), "--libdir", "lib", "--bindir", "bin",
         f"--wrap-mode={mode}", *MESON_PROFILE], env=env, capture=False)
    jobs = max(1, int(os.environ.get("JOBS") or min(os.cpu_count() or 1, 8)))
    run([*ninja, "-C", str(work), "-j", str(jobs)], env=env, capture=False)
    run([*meson, "install", "-C", str(work), "--no-rebuild"],
        env=env, capture=False)
    probe(pc, cc, cflags, ldflags, prefix)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8",
                                     dir=prefix, delete=False) as stamp:
        stamp.write(manifest)
        temp_marker = Path(stamp.name)
    try:
        temp_marker.replace(marker)
    finally:
        temp_marker.unlink(missing_ok=True)
    return prefix


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--build-dir", required=True)
    parser.add_argument("--mode", required=True, choices=("auto", "1"))
    parser.add_argument("--allow-source-init", action="store_true",
                        help="initialize missing pinned GLib/GVDB sources")
    parser.add_argument("--allow-download", action="store_true",
                        help="allow Meson to fetch missing pinned wrap dependencies")
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
