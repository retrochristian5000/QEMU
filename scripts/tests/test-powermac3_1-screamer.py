#!/usr/bin/env python3
"""Static contract checks for the PowerMac3,1 Screamer/DAV model."""
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
AUDIO_KCONFIG = (ROOT / "hw/audio/Kconfig").read_text()
AUDIO_MESON = (ROOT / "hw/audio/meson.build").read_text()
PPC_KCONFIG = (ROOT / "hw/ppc/Kconfig").read_text()
MACIO_H = (ROOT / "include/hw/misc/macio/macio.h").read_text()
MACIO_C = (ROOT / "hw/misc/macio/macio.c").read_text()
MAC_NEWWORLD = (ROOT / "hw/ppc/mac_newworld.c").read_text()
SCREAMER_H = (ROOT / "include/hw/audio/screamer.h").read_text()
SCREAMER_C = (ROOT / "hw/audio/screamer.c").read_text()

def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"missing {label}: {needle}")

require(AUDIO_KCONFIG, "config SCREAMER", "Screamer Kconfig symbol")
require(AUDIO_MESON, "'CONFIG_SCREAMER'", "Screamer Meson selection")
MISC_KCONFIG = (ROOT / "hw/misc/Kconfig").read_text()
require(MISC_KCONFIG, "    select SCREAMER", "MacIO Screamer link dependency")
if "CONFIG_SCREAMER" in MACIO_H:
    raise SystemExit("device CONFIG_SCREAMER must not leak into public MacIO headers")
require(MACIO_H, "ScreamerState screamer;", "MacIO Screamer child")
require(MACIO_C, 'DEFINE_PROP_BOOL("has-screamer"', "MacIO Screamer gate")
require(MAC_NEWWORLD, 'qdev_prop_set_bit(dev, "has-screamer", sawtooth_topology);',
        "Sawtooth-only Screamer property")
require(MACIO_C, "memory_region_add_subregion(&s->bar, 0x14000,",
        "DAV MMIO mapping")
require(MACIO_C,
        "macio_screamer_register_dma(&ns->screamer, &s->dbdma, 0x10, 0x12);",
        "Screamer DB-DMA channels")
for irq in ("NEWWORLD_SCREAMER_IRQ    0x18",
            "NEWWORLD_SCREAMER_TX_IRQ 0x09",
            "NEWWORLD_SCREAMER_RX_IRQ 0x0a"):
    require(MACIO_H, irq, f"Screamer IRQ {irq}")
for rate in ("44100", "29400", "22050", "17640",
             "14700", "11025", "8820", "7350"):
    require(SCREAMER_C, rate, f"Screamer sample rate {rate}")
require(SCREAMER_C, "SCREAMER_CODEC_AMUTE", "output A mute")
require(SCREAMER_C, "SCREAMER_CODEC_CMUTE", "output C mute")
require(SCREAMER_C, "codec_ctrl_regs[2]", "output A attenuation")
require(SCREAMER_C, "codec_ctrl_regs[4]", "output C attenuation")
require(SCREAMER_C, ".big_endian = !(s->regs[SCREAMER_BYTE_SWAP] & 1)",
        "DAV byte-swap handling")
require(SCREAMER_C, "screamer_rx_dma", "capture DMA handler")
require(SCREAMER_C, "timer_mod_ns(s->rx_timer", "paced capture timer")
require(SCREAMER_C, "screamer_save_residual", "DB-DMA residual persistence")
QTEST = (ROOT / "tests/qtest/macio-timer-test.c").read_text()
require(QTEST, "map_sawtooth_keylargo", "Sawtooth downstream MacIO qtest mapping")
require(QTEST, "uninorth_select_cfa1", "UniNorth CFA1 downstream config access")
require(QTEST, "SAWTOOTH_BRIDGE_SLOT    13", "Sawtooth DEC 21154 root slot")
require(QTEST, "SAWTOOTH_MACIO_SLOT     7", "Sawtooth KeyLargo secondary slot")
require(SCREAMER_C, "dma_memory_write", "silence capture progression")
require(SCREAMER_H, "#define SCREAMER_BUFFER_SIZE 0x10000",
        "bounded playback buffer")
require(SCREAMER_C, ".unmigratable = 1", "migration safety guard")
print("PowerMac3,1 Screamer contract: ok")
