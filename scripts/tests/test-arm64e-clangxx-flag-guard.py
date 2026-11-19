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
# The object-level regression must inspect the actual virtual-dispatch
# function, not accept a PAC instruction emitted by an unrelated function.
object_test = (ROOT / "scripts/tests/test-arm64e-object-emission.py").read_text(
    encoding="utf-8"
)
assert 'def disassemble_symbol(objdump, path, symbol):' in object_test
assert '"--disassemble-symbols=" + symbol' in object_test
assert object_test.count('"_whp_virtual")') == 5
assert 'def emit_darwin_arch(cc, initial_target, selected_arch, source, output):' in object_test
assert 'initial_target, "-arch", selected_arch' in object_test
assert 'secure_dis = disassemble_symbol(' in object_test
assert 'unsafe_dis = disassemble_symbol(' in object_test

assert "whp_macos_audit_arm64e_codegen_flags()" in source

variables = ("CC", "CXX", "OBJC", "CFLAGS", "CXXFLAGS",
             "OBJCFLAGS", "CPPFLAGS", "LDFLAGS")
dangerous_flags = (
    "-fno-ptrauth-calls",
    "-fno-ptrauth-vtable-pointer-address-discrimination",
    "-fno-ptrauth-vtable-pointer-type-discrimination",
    "-fno-ptrauth-type-info-vtable-pointer-discrimination",
    "-fno-ptrauth-function-pointer-type-discrimination",
)


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
    for dangerous_flag in dangerous_flags:
        flag = prefix + dangerous_flag
        result = run_case("arm64e", {variable: flag})
        assert result.returncode != 0, (variable, flag, result.stderr)
        assert variable in result.stderr, (variable, flag, result.stderr)
        assert dangerous_flag in result.stderr, (variable, flag, result.stderr)

        # These flags must not block ordinary arm64 compilation.
        result = run_case("arm64", {variable: flag})
        assert result.returncode == 0, (variable, flag, result.stderr)

    result = run_case("arm64e", {variable: prefix + "-fno-omit-frame-pointer"})
    assert result.returncode == 0, (variable, result.stderr)

# No global ban on return-address policy: there are distinct PAC operations.
# We specifically reject the option that defeats arm64e indirect call ABI.
assert run_case("arm64e", {"CXXFLAGS": "-O2 -fno-ptrauth-returns"}).returncode == 0

# Exercise the real symbol filtering helper with a minimal llvm-objdump
# rendering. This catches invalid regex escapes without needing a Mac SDK.
import importlib.util
from unittest import mock

spec = importlib.util.spec_from_file_location(
    "whp_arm64e_object_emission",
    ROOT / "scripts/tests/test-arm64e-object-emission.py",
)
object_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(object_module)
with mock.patch.object(
        object_module, "run",
        return_value="0000000000000000 <_whp_virtual>:\n  0: blraa x8, x9\n"):
    parsed = object_module.disassemble_symbol(
        "llvm-objdump", ROOT / "virtual.o", "_whp_virtual")
    assert "blraa" in parsed
with mock.patch.object(
        object_module, "run",
        return_value="0000000000000000 <_wrong_symbol>:\n  0: blraa x8, x9\n"):
    try:
        object_module.disassemble_symbol(
            "llvm-objdump", ROOT / "virtual.o", "_whp_virtual")
    except AssertionError:
        pass
    else:
        raise AssertionError("unrelated C++ symbol passed PAC call filtering")

print("ARM64e Clang++ authenticated-call/discriminator guards and symbol filtering: verified")
