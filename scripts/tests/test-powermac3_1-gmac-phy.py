#!/usr/bin/env python3
"""Guard the Sawtooth UniNorth GMAC BCM5201 PHY contract."""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
SUNGEM = ROOT / "hw/net/sungem.c"
source = SUNGEM.read_text(encoding="utf-8")
errors: list[str] = []

required = (
    "#define BCM5201_AUXCTLSTATUS              0x18",
    "#define BCM5201_AUXSTATUS                 0x19",
    "#define BCM5201_INTERRUPT                 0x1a",
    "#define BCM5201_AUXMODE2                  0x1b",
    "#define BCM5201_MULTIPHY                  0x1e",
    "#define BCM5201_MULTIPHY_SUPERISOLATE     0x0008",
    "#define BCM5201_MULTIPHY_SERIALMODE       0x0002",
    "uint16_t phy_bmcr;",
    "uint16_t phy_anar;",
    "uint16_t phy_auxctl;",
    "uint16_t phy_interrupt;",
    "uint16_t phy_auxmode2;",
    "uint16_t phy_multiphy;",
    "static void sungem_phy_reset(SunGEMState *s)",
    "static bool sungem_phy_data_path_up(SunGEMState *s)",
    "static bool sungem_phy_aneg_resolved(SunGEMState *s)",
    "static uint16_t sungem_phy_aux_hcd(SunGEMState *s)",
    "static uint16_t sungem_phy_multiphy_hcd(SunGEMState *s)",
    "static void sungem_mii_write(SunGEMState *s, uint8_t phy_addr,",
    "if (phy_addr != s->phy_addr) {",
    "if (val & MII_BMCR_RESET) {",
    "s->phy_bmcr = val & BCM5201_BMCR_WRITABLE;",
    "s->phy_anar = val & BCM5201_ANAR_WRITABLE;",
    "s->phy_auxctl = val & BCM5201_AUXCTL_WRITABLE;",
    "s->phy_interrupt = val & BCM5201_INTERRUPT_WRITABLE;",
    "s->phy_auxmode2 = val & BCM5201_AUXMODE2_WRITABLE;",
    "s->phy_multiphy = val & BCM5201_MULTIPHY_WRITABLE;",
    "case MII_BMCR:",
    "return s->phy_bmcr;",
    "case MII_ANAR:",
    "return s->phy_anar;",
    "case BCM5201_INTERRUPT:",
    "return s->phy_interrupt;",
    "case BCM5201_AUXMODE2:",
    "return s->phy_auxmode2;",
    "case BCM5201_MULTIPHY:",
    "VMSTATE_UINT16_V(phy_bmcr, SunGEMState, 1)",
    "VMSTATE_UINT16_V(phy_multiphy, SunGEMState, 1)",
)
for needle in required:
    if needle not in source:
        errors.append(f"missing PHY contract: {needle}")

for forbidden in (
    "/* XXX TODO */",
    "case MII_BMCR:\n        return MII_BMCR_AUTOEN;",
    "return 3; /* 100FD */",
):
    if forbidden in source:
        errors.append(f"stale primitive PHY behavior remains: {forbidden}")

# BMCR reset/restart are commands rather than persistent readable state.
write_start = source.find("static void sungem_mii_write")
read_start = source.find("static uint16_t __sungem_mii_read", write_start)
if write_start < 0 or read_start < 0:
    errors.append("PHY write/read helper bounds are missing")
else:
    write_body = source[write_start:read_start]
    if "MII_BMCR_RESET" not in write_body:
        errors.append("BMCR reset command must be handled")
    if "MII_BMCR_ANRESTART" in source and "BCM5201_BMCR_WRITABLE" in write_body:
        bmcr_mask_start = source.find("#define BCM5201_BMCR_WRITABLE")
        bmcr_mask_end = source.find("#define BCM5201_ANAR_WRITABLE", bmcr_mask_start)
        if bmcr_mask_start >= 0 and bmcr_mask_end >= 0:
            bmcr_mask = source[bmcr_mask_start:bmcr_mask_end]
            if "MII_BMCR_ANRESTART" in bmcr_mask:
                errors.append("ANRESTART must self-clear instead of persisting in BMCR")

# Isolate blocks the MAC data path but should not masquerade as cable loss.
power_start = source.find("static bool sungem_phy_powered")
link_start = source.find("static bool sungem_phy_link_up", power_start)
path_start = source.find("static bool sungem_phy_data_path_up", link_start)
autoneg_start = source.find("static bool sungem_phy_autoneg", path_start)
if min(power_start, link_start, path_start, autoneg_start) < 0:
    errors.append("PHY power/link/data helper boundaries are missing")
else:
    powered = source[power_start:link_start]
    link = source[link_start:path_start]
    data_path = source[path_start:autoneg_start]
    if "MII_BMCR_ISOLATE" in powered or "MII_BMCR_ISOLATE" in link:
        errors.append("BMCR isolate must not be treated as physical carrier loss")
    if "MII_BMCR_ISOLATE" not in data_path:
        errors.append("BMCR isolate must block the MAC data path")

# Guest advertisement must affect the negotiated mode instead of forcing 100FD.
if "s->phy_anar & BCM5201_ANAR_CAPS" not in source:
    errors.append("autonegotiation must derive common abilities from guest ANAR")
for hcd in (
    "BCM5201_AUXSTATUS_HCD_100TX_FD",
    "BCM5201_AUXSTATUS_HCD_100TX",
    "BCM5201_AUXSTATUS_HCD_10T_FD",
    "BCM5201_AUXSTATUS_HCD_10T",
):
    if hcd not in source:
        errors.append(f"missing negotiated HCD mode: {hcd}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("PowerMac3,1 BCM5201 PHY read/write contract: verified")
