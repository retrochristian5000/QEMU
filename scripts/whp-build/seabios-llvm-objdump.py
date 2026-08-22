#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import struct
import subprocess
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Section:
    name: str
    size: int
    address: int
    offset: int
    alignment: int
    section_type: int


# GNU objdump does not list ELF bookkeeping sections in its -h table.  Keep
# those out of the compatibility table so SeaBIOS sees the same section set.
HIDDEN_SECTION_TYPES = {
    0,   # SHT_NULL
    2,   # SHT_SYMTAB
    3,   # SHT_STRTAB
    4,   # SHT_RELA
    9,   # SHT_REL
}


def _read_elf32_i386_sections(path: pathlib.Path) -> list[Section]:
    data = path.read_bytes()
    if len(data) < 52 or data[:4] != b'\x7fELF':
        raise ValueError(f'not an ELF file: {path}')
    if data[4] != 1:
        raise ValueError(f'expected ELF32 input: {path}')
    if data[5] != 1:
        raise ValueError(f'expected little-endian ELF input: {path}')
    if struct.unpack_from('<H', data, 18)[0] != 3:
        raise ValueError(f'expected EM_386 input: {path}')

    section_offset = struct.unpack_from('<I', data, 32)[0]
    entry_size, section_count, names_index = struct.unpack_from('<HHH', data, 46)
    if entry_size < 40 or section_count == 0:
        raise ValueError(f'ELF file has no usable section table: {path}')
    if names_index >= section_count:
        raise ValueError(f'ELF section-name table index is invalid: {path}')

    def raw_section(index: int) -> tuple[int, ...]:
        offset = section_offset + index * entry_size
        if offset + 40 > len(data):
            raise ValueError(f'ELF section table is truncated: {path}')
        return struct.unpack_from('<IIIIIIIIII', data, offset)

    names_section = raw_section(names_index)
    names_offset, names_size = names_section[4], names_section[5]
    if names_offset + names_size > len(data):
        raise ValueError(f'ELF section-name table is truncated: {path}')
    names = data[names_offset:names_offset + names_size]

    def section_name(offset: int) -> str:
        if offset >= len(names):
            return ''
        end = names.find(b'\0', offset)
        if end < 0:
            end = len(names)
        return names[offset:end].decode('utf-8', errors='replace')

    sections: list[Section] = []
    for index in range(1, section_count):
        section = raw_section(index)
        name_offset, section_type = section[0], section[1]
        if section_type in HIDDEN_SECTION_TYPES:
            continue
        sections.append(Section(
            name=section_name(name_offset),
            size=section[5],
            address=section[3],
            offset=section[4],
            alignment=max(section[8], 1),
            section_type=section_type,
        ))
    return sections


def _alignment_power(alignment: int) -> int:
    if alignment <= 1:
        return 0
    if alignment & (alignment - 1):
        raise ValueError(f'ELF section alignment is not a power of two: {alignment}')
    return alignment.bit_length() - 1


def _gnu_section_table(path: pathlib.Path) -> str:
    lines = [
        'Sections:',
        'Idx Name          Size      VMA       LMA       File off  Algn',
    ]
    for index, section in enumerate(_read_elf32_i386_sections(path)):
        lines.append(
            f'{index:3d} {section.name:<13} {section.size:08x}  '
            f'{section.address:08x}  {section.address:08x}  '
            f'{section.offset:08x}  2**{_alignment_power(section.alignment)}'
        )
    return '\n'.join(lines)


def _strip_llvm_file_header(text: str) -> str:
    lines = text.splitlines()
    for index, line in enumerate(lines):
        if line == 'SYMBOL TABLE:' or line.startswith('RELOCATION RECORDS FOR ['):
            return '\n'.join(lines[index:])
    return ''


def _requested_views(args: list[str]) -> tuple[bool, bool, bool, list[pathlib.Path]]:
    show_sections = False
    show_symbols = False
    show_relocs = False
    inputs: list[pathlib.Path] = []
    for arg in args:
        if arg.startswith('--'):
            continue
        if arg.startswith('-') and len(arg) > 1:
            flags = arg[1:]
            if all(flag in 'htr' for flag in flags):
                show_sections = show_sections or 'h' in flags
                show_symbols = show_symbols or 't' in flags
                show_relocs = show_relocs or 'r' in flags
            continue
        inputs.append(pathlib.Path(arg))
    return show_sections, show_symbols, show_relocs, inputs


def main(argv: list[str]) -> int:
    if not argv:
        print('error: LLVM objdump path is required', file=sys.stderr)
        return 2

    llvm_objdump = argv[0]
    args = argv[1:]
    show_sections, show_symbols, show_relocs, inputs = _requested_views(args)

    # SeaBIOS's compatibility requirement is the GNU -h/-t/-r text format.
    # All other llvm-objdump functionality remains a direct passthrough.
    if not show_sections:
        return subprocess.run([llvm_objdump, *args]).returncode
    if len(inputs) != 1:
        print('error: SeaBIOS objdump compatibility mode requires one input file',
              file=sys.stderr)
        return 2

    input_path = inputs[0]
    try:
        print(f'\n{input_path}:\tfile format elf32-i386\n')
        print(_gnu_section_table(input_path))
    except (OSError, ValueError) as exc:
        print(f'i386-none-elf-objdump: {exc}', file=sys.stderr)
        return 1

    if show_symbols or show_relocs:
        llvm_args: list[str] = []
        if show_symbols:
            llvm_args.append('-t')
        if show_relocs:
            llvm_args.append('-r')
        llvm_args.append(str(input_path))
        result = subprocess.run(
            [llvm_objdump, *llvm_args],
            text=True,
            stdout=subprocess.PIPE,
            check=False,
        )
        if result.returncode:
            return result.returncode
        tail = _strip_llvm_file_header(result.stdout)
        if tail:
            print(f'\n{tail}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
