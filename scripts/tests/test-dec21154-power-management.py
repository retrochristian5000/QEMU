#!/usr/bin/env python3
"""Guard the DEC 21154 rev-05 PCI power-management capability."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
DEC = ROOT / "hw/pci-bridge/dec.c"

dec = DEC.read_text(encoding="utf-8")
errors: list[str] = []

# The rev-05 21154 used by Sawtooth implements the PCI Power Management 1.0
# capability block at configuration offset 0xdc.  Keep this narrowly scoped:
# the test does not claim DEC arbitration, secondary-clock control, or Apple
# board-level sleep wiring that QEMU does not yet emulate.
required = (
    "#define DEC_21154_PM_CAP_OFFSET 0xdc",
    "pci_pm_init(dev, DEC_21154_PM_CAP_OFFSET, errp)",
    "PCI_PM_CAP_VER_1_0",
    "dev->wmask + DEC_21154_PM_CAP_OFFSET + PCI_PM_CTRL",
    "PCI_PM_CTRL_STATE_MASK",
)

for needle in required:
    if needle not in dec:
        errors.append(f"DEC 21154 PM contract missing: {needle}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("DEC 21154 rev-05 power-management contract: verified")
