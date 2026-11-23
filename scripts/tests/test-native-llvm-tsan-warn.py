#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check TSan warning ownership, report policy, and build integration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TSAN = ROOT / "toolchains/llvm-project/compiler-rt/lib/tsan"
RTL = TSAN / "rtl"
WARN = RTL / "tsan_warn.cpp"
RTL_REPORT = RTL / "tsan_rtl_report.cpp"
REPORT = RTL / "tsan_report.cpp"
RUNTIME = RTL / "tsan_rtl.cpp"
HEADER = RTL / "tsan_rtl.h"
CMAKE = RTL / "CMakeLists.txt"
GN = ROOT / (
    "toolchains/llvm-project/llvm/utils/gn/secondary/"
    "compiler-rt/lib/tsan/rtl/BUILD.gn"
)
GO_SH = TSAN / "go/buildgo.sh"
GO_BAT = TSAN / "go/build.bat"


def check_sources() -> None:
    warning = WARN.read_text(encoding="utf-8")
    rtl_report = RTL_REPORT.read_text(encoding="utf-8")
    report = REPORT.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    header = HEADER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    gn = GN.read_text(encoding="utf-8")
    go_sh = GO_SH.read_text(encoding="utf-8")
    go_bat = GO_BAT.read_text(encoding="utf-8")

    # Keep admission, suppression, callbacks, and emission in one owner.
    for declaration in (
        "bool ShouldReport(ThreadState *thr, ReportType typ) {",
        "bool OutputReport(ThreadState *thr, ScopedReport &srep) {",
        "bool PrintWarningSummary() {",
        "void __tsan_on_report(const ReportDesc *rep) {",
    ):
        assert warning.count(declaration) == 1, declaration
        assert declaration not in rtl_report, declaration
    assert warning.count("bool OnReport(const ReportDesc *rep, bool suppressed)") == 2
    assert "SANITIZER_WEAK_CXX_DEFAULT_IMPL" in warning
    assert "SANITIZER_WEAK_DEFAULT_IMPL" in warning
    assert "using namespace __sanitizer;" in warning
    assert "CheckedMutex::CheckNoLocks();" in warning
    assert "if (!flags()->report_bugs || thr->suppress_reports)" in warning

    assert "srep.SymbolizeStackElems();" in warning
    assert "thr->current_report = rep;" in warning
    assert "IsSuppressed(rep->typ, rep->mops[i]->stack, &supp)" in warning
    assert "IsSuppressed(rep->typ, rep->stacks[i], &supp)" in warning
    assert "IsSuppressed(rep->typ, rep->threads[i]->stack, &supp)" in warning
    assert "IsSuppressed(rep->typ, rep->locs[i], &supp)" in warning
    assert "OnReport(rep, pc_or_addr != 0)" in warning
    assert "PrintReport(rep);" in warning
    assert "__tsan_on_report(rep);" in warning
    assert "ctx->nreported++;" in warning
    assert "if (flags()->halt_on_error)" in warning

    # Preserve the two user-facing final summaries, suppression listing, and
    # ordering relative to the finalization callback and exit-code decision.
    assert "ThreadSanitizer: reported %d warnings" in warning
    assert "Found %d data race(s)" in warning
    assert "PrintMatchedSuppressions();" in warning
    assert "return failed;" in warning
    assert "bool PrintWarningSummary();" in header
    assert "bool failed = PrintWarningSummary();" in runtime
    assert runtime.index("ThreadFinalize(thr);") < runtime.index(
        "bool failed = PrintWarningSummary();"
    ) < runtime.index("failed = OnFinalize(failed);")
    assert "return failed ? common_flags()->exitcode : 0;" in runtime

    # Reconstruction and detailed report printing must remain distinct.
    assert "void ReportRace(" in rtl_report
    assert "ScopedReportBase::ScopedReportBase(" in rtl_report
    assert "void PrintReport(const ReportDesc *rep)" in report
    assert "void ReportRace(" not in warning
    assert "void PrintReport(const ReportDesc *rep)" not in warning

    # All builds that previously compiled tsan_rtl_report.cpp need the new TU.
    assert cmake.count("  tsan_warn.cpp\n") == 1
    assert gn.count('"tsan_warn.cpp"') == 1
    assert go_sh.count("../rtl/tsan_warn.cpp") == 1
    assert go_bat.count(r"..\rtl\tsan_warn.cpp") == 1
    assert "tsan_rtl_report.cpp" in cmake
    assert '"tsan_rtl_report.cpp"' in gn


if __name__ == "__main__":
    check_sources()
    print("TSan warning ownership, output policy, and build wiring: verified")
