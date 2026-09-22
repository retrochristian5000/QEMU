#!/usr/bin/env python3
"""Guard dirtyrate against sparse vCPU indexes after CPU hot-unplug."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DIRTYRATE = ROOT / "migration/dirtyrate.c"
DIRTYLIMIT = ROOT / "system/dirtylimit.c"

dirtyrate = DIRTYRATE.read_text(encoding="utf-8")
dirtylimit = DIRTYLIMIT.read_text(encoding="utf-8")
errors: list[str] = []

required_dirtyrate = (
    "g_autofree DirtyPageRecord *records = NULL;",
    "int cpu_index;",
    "record->cpu_index = cpu->cpu_index;",
    "record_dirtypages(&records[index], cpu, start);",
    "stat->rates[i].id = records[i].cpu_index;",
    "trace_dirtyrate_do_calculate_vcpu(records[i].cpu_index, dirtyrate);",
    "g_clear_pointer(&records, g_free);",
    "g_clear_pointer(&stat->rates, g_free);",
)
for needle in required_dirtyrate:
    if needle not in dirtyrate:
        errors.append(f"missing sparse-vCPU dirtyrate guard: {needle}")

for forbidden in (
    "dirty_pages[cpu->cpu_index].start_pages",
    "dirty_pages[cpu->cpu_index].end_pages",
    "stat->rates[i].id = i;",
    "g_free(records);",
):
    if forbidden in dirtyrate:
        errors.append(f"dense allocation still indexed by sparse cpu_index: {forbidden}")

required_dirtylimit = (
    "int cpu_index = stat.rates[i].id;",
    "vcpu_dirty_rate_stat->stat.rates[cpu_index].id = cpu_index;",
    "vcpu_dirty_rate_stat->stat.rates[cpu_index].dirty_rate =",
)
for needle in required_dirtylimit:
    if needle not in dirtylimit:
        errors.append(f"dirtylimit loses sparse vCPU ID: {needle}")

# A one-shot dirty-ring sample stops logging before the CPU-generation check.
# If hotplug invalidates the sample, logging must be restarted before retrying.
for needle in (
    "bool retry;",
    "do {",
    "} while (retry);",
    "if (one_shot) {",
    "global_dirty_log_change(flag, true);",
):
    if needle not in dirtyrate:
        errors.append(f"missing one-shot retry repair: {needle}")

if "goto retry;" in dirtyrate:
    errors.append("dirtyrate retry must not jump past one-shot log restart")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("Dirtyrate sparse-vCPU indexing contract: verified")
