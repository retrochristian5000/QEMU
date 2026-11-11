#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify WHP forbids unsigned C++ virtual calls in the ARM64e build lane.

The production macOS policy function is extracted, executed, and tested
against all compiler and flag sources. Object-level Clang++ verification
lives in test-arm64e-object-emission.py and macOS native toolchain CI.
"""
from pathlib import Path
import os
import subprocess

ROOT = Path(__file__).resolve().parents[2]
policy = (ROOT / "scripts/macos-arch-policy.bash").read_text(
    encoding="utf-8"
)
builder = (ROOT / "scripts/macos-builder.bash").read_text(
    encoding="utf-8"
)
start = policy.index("\nwhp_macos_audit_arm64e_codegen_flags()\n{") + 1
end = policy.index("\n}\n", start) + 2
source = policy[start:end]
assert "whp_macos_audit_arm64e_codegen_flags || exit 1" in builder
assert builder.index("whp_macos_audit_arm64e_codegen_flags || exit 1") < (
    builder.index("whp_macos_audit_linker_driver_flags || exit 1")
)
assert "-fno-ptrauth-calls" in source
assert "whp_macos_audit_arm64e_codegen_flags()" in source

variables = ("CC", "CXX", "OBJC", "CFLAGS", "CXXFLAGS",
             "OBJCFLAGS", "CPPFLAGS", "LDFLAGS")


def run_case(arch, flags=None):
    env = os.environ.copy()
    for variable in variables:
        env.pop(variable, None)
    for variable in ("BASH_ENV", "ENV", "SHELLOPTS", "BASHOPTS",
                     "POSIXLY_CORRECT"):
        env.pop(variable, None)
    env["WHP_MACOS_ARCH"] = arch
    env.update(flags or {})
    return subprocess.run(
        ["bash", "--noprofile", "--norc", "-c",
         source + "\nwhp_macos_audit_arm64e_codegen_flags"],
        env=env, capture_output=True, text=True, check=False,
    )


for arch in ("arm64e", "arm64", "x86_64", "auto"):
    result = run_case(arch)
    assert result.returncode == 0, (arch, result.stderr)

for variable in variables:
    prefix = "clang++ " if variable in ("CXX", "CC", "OBJC") else "-O2 "
    flag = prefix + "-fno-ptrauth-calls"
    result = run_case("arm64e", {variable: flag})
    assert result.returncode != 0, (variable, result.stderr)
    assert variable in result.stderr, (variable, result.stderr)
    assert "-fno-ptrauth-calls" in result.stderr, (variable, result.stderr)

    # The same option is not a pointer-auth ABI violation on ordinary arm64,
    # and the policy must not reject arm64e merely for choosing -O2.
    result = run_case("arm64", {variable: flag})
    assert result.returncode == 0, (variable, result.stderr)
    result = run_case("arm64e", {variable: prefix + "-fno-omit-frame-pointer"})
    assert result.returncode == 0, (variable, result.stderr)

# No global ban on return-address policy: there are distinct PAC operations.
# We specifically reject the option that defeats arm64e indirect call ABI.
assert run_case("arm64e", {"CXXFLAGS": "-O2 -fno-ptrauth-returns"}).returncode == 0

print("ARM64e Clang++ authenticated-call flag guard: verified")
