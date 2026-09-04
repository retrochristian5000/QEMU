#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import re
from pathlib import Path
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
REGISTRY = ROOT / "file-extensions.xml"
INVENTORY = ROOT / "scripts" / "whp-build" / "shell-inventory.bash"


def registry_extension(root: ET.Element, group: str, key: str) -> str:
    node = root.find(f"./{group}/{key}")
    assert node is not None, f"missing registry entry {group}/{key}"
    assert node.text is not None
    return node.text.strip()


def inventory_paths(text: str, variable: str) -> list[Path]:
    match = re.search(rf"{re.escape(variable)}=\(\n(.*?)\n\)", text, re.S)
    assert match is not None, f"missing shell inventory array {variable}"
    relpaths = re.findall(r'"\$SOURCE_DIR/([^\"]+)"', match.group(1))
    return [ROOT / relpath for relpath in relpaths]


xml_root = ET.parse(REGISTRY).getroot()
metadata = xml_root.find("./MetaData")
assert metadata is not None
assert metadata.findtext("CaseSensitive") == "true"
assert metadata.findtext("InternalUsage") == "true"
assert metadata.findtext("LimitedToStd") == "false"

# These are the currently enforced WHP-owned assignments. The registry is
# intentionally expandable; absence from it is not a reason to reject a QEMU
# user-supplied filename.
assert registry_extension(xml_root, "Lang", "POSIXSHELL") == ".sh"
assert registry_extension(xml_root, "Lang", "BASH") == ".bash"
assert registry_extension(xml_root, "Exe", "ELF") == ".ELF"
assert registry_extension(xml_root, "Object", "ELFOBJ") == ".elf"
assert registry_extension(xml_root, "Snd", "WAV") == ".WAV"

inventory_text = INVENTORY.read_text(encoding="utf-8")
posix_scripts = inventory_paths(inventory_text, "WHP_POSIX_BUILD_SCRIPTS")
bash_scripts = inventory_paths(inventory_text, "WHP_BASH_BUILD_SCRIPTS")

for script in posix_scripts:
    assert script.suffix == ".sh", f"POSIX script has non-.sh extension: {script}"
    assert script.is_file(), f"missing POSIX script: {script}"
    first_line = script.read_text(encoding="utf-8").splitlines()[0]
    assert first_line == "#!/bin/sh", f"POSIX launcher has non-POSIX shebang: {script}"

for script in bash_scripts:
    assert script.suffix == ".bash", f"Bash implementation has non-.bash extension: {script}"
    assert script.is_file(), f"missing Bash implementation: {script}"

vof_makefile = (ROOT / "pc-bios" / "vof" / "Makefile").read_text(encoding="utf-8")
s390_makefile = (ROOT / "pc-bios" / "s390-ccw" / "Makefile").read_text(encoding="utf-8")
pc_bios_meson = (ROOT / "pc-bios" / "meson.build").read_text(encoding="utf-8")
wav_audio = (ROOT / "audio" / "wavaudio.c").read_text(encoding="utf-8")

assert "vof.ELF:" in vof_makefile
assert "vof.elf:" not in vof_makefile
assert "s390-ccw.ELF:" in s390_makefile
assert "s390-ccw.elf:" not in s390_makefile
assert "output: 'seabios-grub.ELF'" in pc_bios_meson
assert "scripts/meson-build-seabios.bash" in pc_bios_meson
assert '"qemu.WAV"' in wav_audio

# Deliberately no runtime path/parser checks live here. WHP extension policy
# governs fork-owned source and generated defaults, not names supplied by users.
print("WHP file-extension standard: verified for fork-owned files")
