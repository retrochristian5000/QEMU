#!/usr/bin/env python3
"""Static interface guard; runtime QTest requires an evidence-based machine."""
from pathlib import Path
r = Path(__file__).resolve().parents[2]
src = (r / "hw/display/twowire_led_panel.c").read_text()
hdr = (r / "include/hw/display/twowire-led-panel.h").read_text()
cfg = (r / "hw/display/Kconfig").read_text()
meson = (r / "hw/display/meson.build").read_text()
target = (r / "configs/devices/trimedia-softmmu/default.mak").read_text()
for indicator in ("POWER", "ETHERNET", "WIRELESS", "DSL", "INTERNET"):
    assert f'"{indicator}"' in src
for channel in ("POWER_GREEN", "POWER_ORANGE", "POWER_RED",
                "ETHERNET_GREEN", "WIRELESS_GREEN", "DSL_GREEN",
                "INTERNET_GREEN", "INTERNET_RED"):
    assert "TWOWIRE_" + channel in hdr
assert "led_create_simple_with_reset(" in src
assert "led_add_change_notifier(" in src
assert "qemu_graphic_console_create(" in src
assert "qemu_console_update_full(" in src
assert "qdev_init_gpio_in_named(" in src
assert "timer_new_" not in src and "sysbus_init_mmio" not in src
assert "config TWOWIRE_LED_PANEL" in cfg
assert "select LED" in cfg.split("config TWOWIRE_LED_PANEL", 1)[1]
assert "CONFIG_TWOWIRE_LED_PANEL" in meson
assert "CONFIG_TWOWIRE_LED_PANEL=y" in target
print("2Wire LED panel static contract: verified")
