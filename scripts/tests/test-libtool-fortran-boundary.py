#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard optional Libtool Fortran probes against guest toolchain contamination."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "ensure-libtool.py"
SPEC = importlib.util.spec_from_file_location("whp_libtool_fortran_boundary", SCRIPT)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot import the native Libtool bootstrap helper")
helper = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(helper)


def main() -> int:
    required = {
        "FC", "F77", "F90", "FCFLAGS", "FFLAGS",
        "GNU_FC", "GNU_F77", "GNU_FCFLAGS", "GNU_FFLAGS",
    }
    assert required.issubset(helper.TARGET_FORTRAN_ENV), (
        "incomplete native Libtool Fortran environment boundary"
    )

    env = {
        name: "/guest/fortran/unsupported"
        for name in helper.TARGET_FORTRAN_ENV
    }
    native = {
        "CC": "/native/clang",
        "CXX": "/native/clang++",
        "AR": "/native/llvm-ar",
        "MAKE": "/native/gmake",
        "PATH": "/native/bin",
    }
    env.update(native)
    helper.isolate_host_fortran_env(env)
    leaking = sorted(set(env).intersection(helper.TARGET_FORTRAN_ENV))
    assert not leaking, f"guest Fortran settings survived: {leaking}"
    for name, value in native.items():
        assert env.get(name) == value, f"native {name} changed unexpectedly"

    # A no-Fortran host must still reach native compiler discovery.
    # Merely defining the sanitizer is insufficient if bootstrap omits it.
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.count("    isolate_host_fortran_env(env)\n") == 1, (
        "native Libtool bootstrap does not apply Fortran isolation"
    )
    print("WHP Libtool optional Fortran host boundary: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
