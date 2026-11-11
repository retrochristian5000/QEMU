#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard LLDB's C++23 incomplete-type unique_ptr fix without Apple SDK edits.

This is a source-layout and compiler smoke test, NOT a full LLDB build.
"""

from pathlib import Path
import re
import shutil
import subprocess
import tempfile

root = Path(__file__).resolve().parents[2]
llvm = root / "toolchains/llvm-project"
if not (llvm / "lldb/include/lldb/Core/EmulateInstruction.h").is_file():
    llvm = root / "llvm-project"
header = llvm / "lldb/include/lldb/Core/EmulateInstruction.h"
implementation = llvm / "lldb/source/Core/EmulateInstruction.cpp"
if not header.is_file() or not implementation.is_file():
    raise SystemExit("error: pinned LLVM LLDB EmulateInstruction sources missing")

h = header.read_text(encoding="utf-8")
cpp = implementation.read_text(encoding="utf-8")
declaration = re.search(
    r"SingleStepBreakpointLocationsPredictor\s*\(\s*"
    r"std::unique_ptr<EmulateInstruction>\s+emulator_up\s*\)\s*;",
    h,
)
destructor = re.search(
    r"~SingleStepBreakpointLocationsPredictor\s*\(\s*\)\s*;",
    h,
)
implementation_ctor = re.search(
    r"SingleStepBreakpointLocationsPredictor::"
    r"SingleStepBreakpointLocationsPredictor\s*\(\s*"
    r"std::unique_ptr<EmulateInstruction>\s+emulator_up\s*\)",
    cpp,
)
implementation_dtor = re.search(
    r"~SingleStepBreakpointLocationsPredictor\s*\(\s*\)\s*=\s*default\s*;",
    cpp,
)
if not all((declaration, destructor, implementation_ctor, implementation_dtor)):
    raise SystemExit(
        "error: LLDB C++23 incomplete-type lifetime guard regressed; "
        "restore out-of-line constructor/destructor declarations and definitions"
    )
compiler = shutil.which("clang++")
if compiler is None:
    raise SystemExit("error: clang++ is required for LLDB C++23 ABI smoke test")

# Mirror the incomplete-type ownership relationship in an isolated fixture.
# The declaration must not instantiate std::unique_ptr's cleanup while the
# pointee is forward declared; the destructor and constructor must be defined
# after its full definition. Compile with the native toolchain's libc++.
fixture = """\
#include <memory>
#include <utility>
class EmulateInstruction;
class Predictor {
public:
  explicit Predictor(std::unique_ptr<EmulateInstruction> p);
  virtual ~Predictor();
private:
  std::unique_ptr<EmulateInstruction> emulator_;
};
class EmulateInstruction { public: virtual ~EmulateInstruction() = default; };
Predictor::Predictor(std::unique_ptr<EmulateInstruction> p)
    : emulator_(std::move(p)) {}
Predictor::~Predictor() = default;
void use(Predictor &value) { (void)value; }
"""
with tempfile.TemporaryDirectory(prefix="whp-lldb-cxx23-") as temp:
    source = Path(temp) / "incomplete-lifetime.cpp"
    source.write_text(fixture, encoding="utf-8")
    result = subprocess.run(
        [compiler, "-std=c++23", "-fsyntax-only", str(source)],
        text=True, capture_output=True, check=False,
    )
    if result.returncode:
        raise SystemExit(
            "error: native C++23 pointer-lifetime smoke test failed:\n"
            + result.stderr[-4000:]
        )

print("LLDB C++23 incomplete-type lifetime: declarations and smoke test pass")
