#!/usr/bin/env python3
"""Guard the Sawtooth UniNorth GMAC BCM5201 PHY read contract."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SUNGEM = ROOT / "hw/net/sungem.c"
source = SUNGEM.read_text(encoding="utf-8")
errors: list[str] = []

required = (
    "#define BCM5201_AUXCTLSTATUS              0x18",
    "#define BCM5201_AUXCTLSTATUS_DUPLEX       0x0001",
    "#define BCM5201_AUXCTLSTATUS_SPEED100     0x0002",
    "#define BCM5201_AUXCTLSTATUS_ANEG         0x0008",
    "#define BCM5201_AUXSTATUS                 0x19",
    "#define BCM5201_AUXSTATUS_HCD_100TX_FD    0x0500",
    "static bool sungem_phy_link_up(SunGEMState *s)",
    "return !qemu_get_queue(s->nic)->link_down;",
    "case MII_BMCR:",
    "return MII_BMCR_AUTOEN;",
    "case MII_BMSR:",
    "BCM5201_BMSR_CAPS",
    "MII_BMSR_AN_COMP | MII_BMSR_LINK_ST",
    "case MII_ANAR:",
    "return BCM5201_ANAR_CAPS;",
    "case MII_ANLPAR:",
    "BCM5201_ANAR_CAPS | MII_ANLPAR_ACK",
    "case MII_ANER:",
    "MII_ANER_NWAY",
    "case BCM5201_AUXCTLSTATUS:",
    "BCM5201_AUXCTLSTATUS_ANEG",
    "BCM5201_AUXCTLSTATUS_SPEED100",
    "BCM5201_AUXCTLSTATUS_DUPLEX",
    "case BCM5201_AUXSTATUS:",
    "BCM5201_AUXSTATUS_ANEG_COMPLETE",
    "BCM5201_AUXSTATUS_LP_ABILITY",
    "BCM5201_AUXSTATUS_HCD_100TX_FD",
    "BCM5201_AUXSTATUS_LINK",
)
for needle in required:
    if needle not in source:
        errors.append(f"missing PHY read contract: {needle}")

# Retire the old contradictory shortcuts.
for forbidden in (
    "case MII_BMCR:\n        return 0;",
    "return MII_ANLPAR_TXFD;",
    "case 0x18: /* 5201 AUX status */",
    "return 3; /* 100FD */",
):
    if forbidden in source:
        errors.append(f"stale primitive PHY read remains: {forbidden}")

# Capability bits are static; negotiated status is conditional on link.
read_start = source.find("static uint16_t __sungem_mii_read")
read_end = source.find("static uint16_t sungem_mii_read", read_start + 1)
if read_start < 0 or read_end < 0:
    errors.append("PHY read helper bounds are missing")
else:
    read_body = source[read_start:read_end]
    if "link_up ? MII_BMSR_AN_COMP | MII_BMSR_LINK_ST : 0" not in read_body:
        errors.append("BMSR link/aneg status must follow backend link")
    if "return link_up ? (BCM5201_ANAR_CAPS | MII_ANLPAR_ACK) : 0;" not in read_body:
        errors.append("ANLPAR must not advertise a live partner while link is down")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 BCM5201 PHY read contract: verified")
