#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard fixed-identity ATI Rage 128 Pro and Radeon RV100 QOM profiles.

A common renderer is allowed; one device type changing into the other
through mutable properties is not. Runtime QMP device-list-properties is
also covered by tests/qtest/device-introspect-test.c.
"""
from pathlib import Path

root = Path(__file__).resolve().parents[2]
ati = (root / "hw/display/ati.c").read_text(encoding="utf-8")
header = (root / "hw/display/ati_int.h").read_text(encoding="utf-8")
sawtooth = (root / "hw/ppc/powermac3_1.c").read_text(encoding="utf-8")
fuloong = (root / "hw/mips/fuloong2e.c").read_text(encoding="utf-8")
intro = (root / "tests/qtest/device-introspect-test.c").read_text(
    encoding="utf-8")
amiga = (root / "docs/system/ppc/amigang.rst").read_text(encoding="utf-8")
pci = (root / "hw/pci/pci.c").read_text(encoding="utf-8")

for name, qom in (
    ("TYPE_ATI_VGA", "ati-vga"),
    ("TYPE_ATI_RAGE128P", "ati-rage128p"),
    ("TYPE_ATI_RV100", "ati-rv100"),
):
    assert f'#define {name} "{qom}"' in header, name

assert "#define PCI_DEVICE_ID_ATI_RAGE128_PF 0x5046" in header
assert "#define PCI_DEVICE_ID_ATI_RADEON_QY 0x5159" in header
assert "char *model;" not in header
assert "ati_model_aliases" not in ati
assert 'DEFINE_PROP_STRING("model",' not in ati
assert 'DEFINE_PROP_UINT16("x-device-id",' not in ati

def section(begin, end):
    return ati.split(begin, 1)[1].split(end, 1)[0]


base_class = section("static void ati_vga_class_init(", "static void ati_vga_init(")
base_init = section("static void ati_vga_init(", "static const TypeInfo ati_vga_info")
rage_class = section("static void ati_rage128p_class_init(",
                     "static void ati_rv100_instance_init(")
radeon_init = section("static void ati_rv100_instance_init(",
                      "static void ati_rv100_class_init(")
radeon_class = section("static void ati_rv100_class_init(",
                       "static const TypeInfo ati_rage128p_info")
types = ati.split("static const TypeInfo ati_rage128p_info", 1)[1]

# The legacy -vga ati uses the one and only Rage 128 identity.
assert "s->dev_id = PCI_DEVICE_ID_ATI_RAGE128_PF;" in base_init
assert "k->device_id = PCI_DEVICE_ID_ATI_RAGE128_PF;" in base_class
assert 'pci_create_simple(bus, -1, "ati-vga")' in pci

# Each canonical device must have its own class, no shared model switch.
assert "k->device_id = PCI_DEVICE_ID_ATI_RAGE128_PF;" in rage_class
assert "ATI_VGA(obj)->dev_id = PCI_DEVICE_ID_ATI_RADEON_QY;" in radeon_init
assert "k->device_id = PCI_DEVICE_ID_ATI_RADEON_QY;" in radeon_class
for token in (
    ".name = TYPE_ATI_RAGE128P,",
    ".name = TYPE_ATI_RV100,",
    ".parent = TYPE_ATI_VGA,",
    ".instance_init = ati_rv100_instance_init,",
    ".class_init = ati_rv100_class_init,",
    "type_register_static(&ati_rage128p_info);",
    "type_register_static(&ati_rv100_info);",
):
    assert token in types, token

# The hardware default is a Rage 128, not a device-id-switched Radeon.
assert 'pci_new(PCI_DEVFN(16, 0), "ati-rage128p")' in sawtooth
assert 'qdev_prop_set_uint32(DEVICE(dev), "vgamem_mb", 16)' in sawtooth
assert '"model", "rage128p"' not in sawtooth
assert 'pci_new(-1, "ati-rv100")' in fuloong
assert 'qdev_prop_set_uint64(dev, "x-linear-aper-size", 16 * MiB)' in fuloong
assert '"x-device-id"' not in fuloong
assert "-device ati-rv100,romfile=" in amiga

# QMP properties and HMP help must not reintroduce an identity switch.
for name in ('"ati-vga"', '"ati-rage128p"', '"ati-rv100"'):
    assert name in intro
for token in (
    'property_list_has_name(props, "vgamem_mb")',
    'property_list_has_name(props, "model")',
    'property_list_has_name(props, "x-device-id")',
    'strstr(help, "model=")',
    'strstr(help, "x-device-id=")',
):
    assert token in intro
assert 'g_assert_false(property_list_has_name(props, "model"));' in intro
assert 'g_assert_false(property_list_has_name(props, "x-device-id"));' in intro

print("ATI Rage 128 Pro and RV100 fixed device profiles: verified")
