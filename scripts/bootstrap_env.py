#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sanitize child environments for QEMU's native host-tool bootstraps."""

from __future__ import annotations

import os
import pathlib
import platform
import subprocess
import re
import shlex
import sys
import tempfile
from collections.abc import Mapping

# Never erase the caller's environment. Preserve PATH, HOME, SDKROOT,
# DEVELOPER_DIR, CC_FOR_BUILD and WHP seed identities. Tool-specific
# executables are restored explicitly by each native bootstrap stage.
DROP = frozenset("""
BASH_ENV ENV POSIXLY_CORRECT MAKEFLAGS MFLAGS GNUMAKEFLAGS MAKEFILES
MAKEOVERRIDES MAKELEVEL MAKE MAKE_CMD CC CXX CPP CXXCPP OBJC OBJCXX FC F77 F90
AR ARFLAGS AS LD NM RANLIB STRIP OBJCOPY OBJDUMP DLLTOOL
CFLAGS CXXFLAGS CPPFLAGS LDFLAGS OBJCFLAGS OBJCXXFLAGS FCFLAGS FFLAGS LIBS
LIBRARY_PATH CPATH C_INCLUDE_PATH CPLUS_INCLUDE_PATH OBJC_INCLUDE_PATH
PKG_CONFIG PKG_CONFIG_PATH PKG_CONFIG_LIBDIR PKG_CONFIG_SYSROOT_DIR
CMAKE_PREFIX_PATH CONFIG_SITE CONFIG_CACHE CACHE_FILE ACLOCAL_PATH
AUTOM4TE_CFG AUTOM4TE_CACHE WARNINGS M4 AUTOPOINT LIBTOOL LIBTOOLIZE
build_alias host_alias target_alias
LD_LIBRARY_PATH LD_PRELOAD COMPILER_PATH GCC_EXEC_PREFIX
DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
DYLD_INSERT_LIBRARIES ASAN_OPTIONS LSAN_OPTIONS UBSAN_OPTIONS
TSAN_OPTIONS MSAN_OPTIONS
""".split())
DROP_PREFIXES = (
    "ac_cv_", "gl_cv_", "am_cv_", "gt_cv_", "lt_cv_", "make_cv_",
    "sed_cv_", "bash_cv_", "ac_env_",
)


def clean_host_environment(source: Mapping[str, str]) -> dict[str, str]:
    return {
        key: val for key, val in source.items()
        if key not in DROP and not key.startswith(DROP_PREFIXES)
    }



# Ordinary CFLAGS remain QEMU-owned. Each managed host bootstrap may opt in to
# these two independent pools; no global ABI, target, sanitizer or LTO options
# should ever be forwarded to a different project's configure or make.
_COMMON_CFLAG = re.compile(r"-O[0-3sgz]|-g[0-3]?|-pipe|-fPIC|-fpic")
_LOCAL_CFLAG = re.compile(r"-(?:W|f)[A-Za-z0-9_.,=+/-]+|-[DUI][^\s]+")
_FORBIDDEN_CFLAG = (
    "-flto", "-fno-lto", "-fsanitize", "-fno-sanitize",
    "-fprofile", "-fcoverage", "-fuse-ld", "-fplugin",
    "-fuse-linker-plugin", "-fno-use-linker-plugin",
)


def select_bootstrap_cflags(
    repository: str, cc: str, source: Mapping[str, str] | None = None
) -> str:
    """Return supported, non-ABI-changing flags for one native C bootstrap.

    WHP_BOOTSTRAP_COMMON_CFLAGS applies only to consumers of this function.
    WHP_BOOTSTRAP_<REPOSITORY>_CFLAGS is a separate, explicit repository lane.
    Inherited CFLAGS, target flags, CPU architecture, LTO and sanitizers never
    participate. Unsupported individual options are reported and skipped.
    """
    if not re.fullmatch(r"[a-z][a-z0-9_]*", repository):
        raise ValueError(f"invalid bootstrap repository name: {repository}")
    if source is None:
        source = os.environ
    common = "WHP_BOOTSTRAP_COMMON_CFLAGS"
    local = f"WHP_BOOTSTRAP_{repository.upper()}_CFLAGS"
    requested: list[tuple[str, str]] = []
    for variable in (common, local):
        try:
            fragments = shlex.split(source.get(variable, ""))
        except ValueError as exc:
            raise ValueError(f"{variable} has invalid quoting: {exc}") from exc
        requested.extend((variable, fragment) for fragment in fragments)
    if not requested:
        return ""

    env = clean_host_environment(source)
    # The compiler identity was established separately by the native cc.sh
    # adapter; these probes must not consume the target CC or linker settings.
    env.pop("LD_PRELOAD", None)
    env.pop("COMPILER_PATH", None)
    env.pop("GCC_EXEC_PREFIX", None)
    selected: list[str] = []
    with tempfile.TemporaryDirectory(prefix="whp-bootstrap-cflags-") as name:
        directory = pathlib.Path(name)
        test = directory / "probe.c"
        output = directory / "probe"
        test.write_text(
            "#include <stddef.h>\n"
            "int main(void) { return sizeof(size_t) == 0; }\n",
            encoding="utf-8",
        )
        for variable, fragment in requested:
            is_common = variable == common
            structurally_safe = (
                not any(c.isspace() or c == "\0" for c in fragment)
                and not fragment.startswith(_FORBIDDEN_CFLAG)
                and (
                    bool(_COMMON_CFLAG.fullmatch(fragment))
                    if is_common else
                    bool(_COMMON_CFLAG.fullmatch(fragment) or
                         _LOCAL_CFLAG.fullmatch(fragment))
                )
                and not fragment.startswith(("-Wl,", "-Wa,", "-Wp,"))
            )
            if not structurally_safe:
                print(
                    f"WHP {repository}: ignoring nonportable {variable} "
                    f"fragment: {fragment!r}", file=sys.stderr,
                )
                continue
            probe = subprocess.run(
                [cc, *selected, fragment, str(test), "-o", str(output)],
                cwd=directory, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False,
            )
            diagnostics = (probe.stdout + probe.stderr).lower()
            if probe.returncode or (
                "unknown warning option" in diagnostics
                or "unrecognized command-line option" in diagnostics
            ):
                print(
                    f"WHP {repository}: compiler rejected {variable} "
                    f"fragment: {fragment!r}", file=sys.stderr,
                )
                continue
            selected.append(fragment)
    return " ".join(selected)


def select_native_sdk(root: pathlib.Path) -> str:
    """Preserve the exact selected Xcode/CLT SDK for all native tools."""
    if platform.system() != "Darwin":
        return ""
    script = (
        '. "$1" || exit 1; '
        'if [ -n "$2" ]; then '
        'whp_apple_check_sdkroot "$2" || exit 1; '
        'printf "%s\\n" "$2"; '
        'else whp_apple_find_sdk; fi'
    )
    result = subprocess.run(
        [
            "/bin/sh", "-c", script, "whp-native-bootstrap-sdk",
            str(root / "scripts/whp-build/macos-developer-tools.sh"),
            os.environ.get("SDKROOT", ""),
        ],
        text=True, capture_output=True, check=False,
    )
    sdkroot = result.stdout.strip()
    if (
        result.returncode or not sdkroot or "\n" in sdkroot or
        not pathlib.Path(sdkroot).is_dir()
    ):
        raise RuntimeError(
            "selected macOS SDK is unavailable for native bootstrap"
            + (f": {result.stderr.strip()}" if result.stderr.strip() else "")
        )
    return sdkroot


def select_native_cc(root: pathlib.Path) -> str:
    """Resolve the validated C role via the existing cc.sh adapter."""
    result = subprocess.run(
        [str(root / "cc.sh"), "--print-cc"],
        text=True, capture_output=True, check=False,
    )
    path = result.stdout.strip()
    if (
        result.returncode or not path or "\n" in path or
        not pathlib.Path(path).is_absolute() or
        not pathlib.Path(path).is_file() or not os.access(path, os.X_OK)
    ):
        detail = result.stderr.strip()
        raise RuntimeError(
            "QEMU cc.sh could not select a valid native bootstrap compiler"
            + (f": {detail}" if detail else "")
        )
    return path
