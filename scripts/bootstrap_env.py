#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Sanitize child environments for QEMU's native host-tool bootstraps."""

from __future__ import annotations

import os
import pathlib
import platform
import subprocess
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
LD_LIBRARY_PATH DYLD_LIBRARY_PATH DYLD_FALLBACK_LIBRARY_PATH
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
