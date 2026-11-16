#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the QEMU host C dialect without exporting -std into dependencies.

The chosen QEMU artifact CC is checked, not the early CC_FOR_BUILD seed.
The QEMU configure/Meson stage still owns ABI, SDK, linker and library checks.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile

# GCC 14 reports 202000L for gnu23; Clang 17 reports 202311L.
# A successful probe demonstrates a dialect subset, not ISO certification.
C_STANDARD_VERSION = {
    "c99": 199901, "gnu99": 199901,
    "c11": 201112, "gnu11": 201112,
    "c17": 201710, "gnu17": 201710,
    "c23": 202000, "gnu23": 202000,
}


def conflicting_ambient_flags(env: dict[str, str]) -> list[str]:
    conflicts: list[str] = []
    for variable in ("CFLAGS", "CPPFLAGS", "OBJCFLAGS", "CXXFLAGS"):
        try:
            tokens = shlex.split(env.get(variable, ""))
        except ValueError as exc:
            raise ValueError(f"cannot parse {variable}: {exc}") from exc
        for token in tokens:
            if token.startswith(("-std=", "/std:")) or token in ("-std", "-ansi"):
                conflicts.append(f"{variable}: {token}")
    return conflicts


def check(compiler: str, standard: str, env: dict[str, str]) -> None:
    if standard not in C_STANDARD_VERSION:
        raise ValueError("unsupported C standard: " + standard)
    inherited = conflicting_ambient_flags(env)
    if inherited:
        raise ValueError(
            "global language-standard flags conflict with component-owned "
            "standards: " + "; ".join(inherited)
            + ". Use QEMU_C_STANDARD/QEMU_CXX_STANDARD for QEMU or "
            "dependency-specific flags for other builds."
        )
    try:
        driver = shlex.split(compiler)
    except ValueError as exc:
        raise ValueError(f"invalid C compiler command: {exc}") from exc
    if not driver or any(any(c in arg for c in "\n\r\0") for arg in driver):
        raise ValueError("selected C compiler command is empty or malformed")

    minimum = C_STANDARD_VERSION[standard]
    source = f"""\
#ifndef __STDC_VERSION__
#error compiler has no C standard identity
#endif
#if __STDC_VERSION__ < {minimum}L
#error requested C dialect is not available
#endif
#ifdef __cplusplus
#error compiler selected C++ instead of C
#endif
#define WHP_VARIADIC_MACRO(...) (__VA_ARGS__)
static int whp_probe(int *restrict number) {{
    return WHP_VARIADIC_MACRO(*number);
}}
#if __STDC_VERSION__ >= 201112L
_Static_assert(sizeof(int) >= 2, "C11 static assertions");
#endif
#if __STDC_VERSION__ >= 202000L
static typeof(1) whp_c23_value = 7;
static void *whp_c23_null = nullptr;
#endif
int main(void) {{
    int value = 7;
    return whp_probe(&value) == 7 ? 0 : 1;
}}
"""
    with tempfile.TemporaryDirectory(prefix="whp-c-standard-") as directory:
        obj = Path(directory) / "probe.o"
        args = [*driver, f"-std={standard}", "-Werror", "-x", "c", "-c",
                "-", "-o", str(obj)]
        try:
            result = subprocess.run(args, input=source, text=True,
                                    stdout=subprocess.PIPE,
                                    stderr=subprocess.PIPE, env=env,
                                    timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(
                f"C standard {standard} probe failed for {compiler}: {exc}"
            ) from exc
        if result.returncode or not obj.is_file() or not obj.stat().st_size:
            detail = (result.stderr or result.stdout).strip()
            raise RuntimeError(
                f"C standard {standard} is not supported by selected QEMU "
                f"C compiler {compiler} (exit {result.returncode}; "
                f"minimum __STDC_VERSION__={minimum}L)"
                + ("\n" + detail if detail else "\nno object file produced")
            )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compiler", required=True)
    parser.add_argument("--standard", required=True)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args(argv)
    try:
        check(args.compiler, args.standard, os.environ.copy())
    except (RuntimeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if args.check:
        print(f"WHP QEMU C standard {args.standard}: supported by {args.compiler}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
