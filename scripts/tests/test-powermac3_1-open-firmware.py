#!/usr/bin/env python3
"""Verify the PowerMac3,1 -> OpenBIOS board identity ABI."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROFILE = (ROOT / "hw/ppc/powermac3_1.c").read_text()
GENERIC = (ROOT / "hw/ppc/mac_newworld.c").read_text()


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")


require(PROFILE, '#define POWERMAC3_1_OF_BOARD_ID_FILE "etc/ppc/board-id"',
        "board-id fw_cfg filename")
require(PROFILE, 'static char powermac3_1_of_board_id[] = "PowerMac3,1";',
        "NUL-terminated Open Firmware model payload")
require(PROFILE, "fw_cfg_add_file(fw_cfg, POWERMAC3_1_OF_BOARD_ID_FILE,",
        "board-id publication")
require(PROFILE, "sizeof(powermac3_1_of_board_id)",
        "NUL-inclusive board-id size")
require(PROFILE, "NUL-terminated ASCII Open Firmware model identifier",
        "ABI format documentation")

# Keep the explicit historical machine opt-in. Generic mac99 must not acquire
# the board id merely because it shares the Core99 implementation.
if "etc/ppc/board-id" in GENERIC:
    raise SystemExit("generic mac99 must not publish the PowerMac3,1 board id")

print("PowerMac3,1 OpenBIOS board-id ABI: ok")
