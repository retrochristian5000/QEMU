#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify the Sawtooth modem slot, KeyLargo reset, and backend integration."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
machine = (ROOT / "hw/ppc/mac_newworld.c").read_text()
gpio = (ROOT / "hw/misc/macio/gpio.c").read_text()
gpio_h = (ROOT / "include/hw/misc/macio/gpio.h").read_text()
modem = (ROOT / "chardev/modem.c").read_text()
modem_h = (ROOT / "include/chardev/modem.h").read_text()
unit = (ROOT / "tests/unit/test-modem-voice.c").read_text()

for token in (
    'cms->modem_present = true;',
    'object_dynamic_cast(obj, MACHINE_TYPE_NAME("powermac3_1"))',
    'object_property_add_bool(obj, "modem", core99_get_modem,',
    'sawtooth_topology && core99_machine->modem_present &&',
    'defaults_enabled()',
    'modem_chr ? modem_chr : serial_hd(0)',
    'qdev_connect_gpio_out_named(gpio, "modem-reset", 0,',
    'qemu_allocate_irq(sawtooth_modem_reset, modem_chr, 0)',
    'qemu_modem_hardware_reset(opaque);',
):
    assert token in machine, f"missing Sawtooth modem wiring: {token}"

for token in (
    "#define MACIO_GPIO_MODEM_RESET_OFFSET 0x6d",
    "qemu_irq modem_reset;",
):
    assert token in gpio_h, f"missing modem GPIO declaration: {token}"

for token in (
    'qdev_init_gpio_out_named(DEVICE(obj), &s->modem_reset, "modem-reset", 1)',
    "bool reset = (value & OUT_ENABLE) && !(value & OUT_DATA);",
    "if (reset != was_reset)",
    "qemu_set_irq(s->modem_reset, reset);",
):
    assert token in gpio, f"missing modem GPIO behavior: {token}"

assert "void qemu_modem_hardware_reset(Chardev *chr)" in modem
assert "void qemu_modem_hardware_reset(Chardev *chr);" in modem_h
assert "fifo8_reset(&modem->outbuf);" in modem
assert "fifo8_reset(&modem->net_txbuf);" in modem
assert "modem_reset(modem);" in modem
assert 'g_test_add_func("/modem/hardware-reset", test_hardware_reset)' in unit

print("Sawtooth modem slot, optional presence, and reset path: wired")
