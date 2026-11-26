#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Build and inspect the IDE ROM; optionally boot a disposable test disk."""

import argparse
import pathlib
import struct
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'roms' / 'ide-optionrom'


def run(*args):
    subprocess.run([str(arg) for arg in args], check=True)


def check_image(path):
    data = path.read_bytes()
    assert data[:2] == b'\x55\xaa'
    assert len(data) == data[2] * 512
    assert 0 < len(data) <= 2048, 'first-stage IDE ROM exceeds allocation'
    assert sum(data) % 256 == 0
    pci, pnp = struct.unpack_from('<HH', data, 0x18)
    assert pci == 0 and 0x1c <= pnp < len(data) - 32
    assert data[pnp:pnp + 6] == b'$PnP\x01\x02'
    assert sum(data[pnp:pnp + 32]) % 256 == 0
    bcv, dv, bev = struct.unpack_from('<HHH', data, pnp + 0x16)
    assert pnp + 32 <= bcv < len(data) - 1 and dv == bev == 0
    return data


def check_elf(path, raw):
    data = path.read_bytes()
    assert data[:6] == b'\x7fELF\x01\x01'
    kind, machine, _, entry, phoff, shoff = struct.unpack_from('<HHIIII', data, 16)
    assert (kind, machine, entry) == (2, 3, 0)
    _, phentsize, phnum, shentsize, shnum, shstrndx = struct.unpack_from(
        '<HHHHHH', data, 40)
    segments = [struct.unpack_from('<IIIIIIII', data, phoff + i * phentsize)
                for i in range(phnum)]
    loads = [p for p in segments if p[0] == 1]
    assert len(loads) == 1
    _, offset, vaddr, paddr, filesz, memsz, flags, _ = loads[0]
    assert (vaddr, paddr, filesz, memsz, flags) == (0, 0, len(raw), len(raw), 5)
    assert data[offset:offset + filesz] == raw
    headers = [struct.unpack_from('<IIIIIIIIII', data, shoff + i * shentsize)
               for i in range(shnum)]
    names_header = headers[shstrndx]
    names = data[names_header[4]:names_header[4] + names_header[5]]
    allocated = [(names[h[0]:].split(b'\0', 1)[0], h)
                 for h in headers if h[2] & 2 and h[5]]
    assert len(allocated) == 1 and allocated[0][0] == b'.text'
    header = allocated[0][1]
    assert (header[3], header[4], header[5]) == (0, offset, len(raw))


def check_unexpected_section(work, linker, label):
    source = work / f'{label}-unexpected.S'
    source.write_text('.code16\n.text\n.global _start\n_start:\n'
                      '.word 0xaa55\n.byte 1\n.balign 512, 0\n'
                      '.data\n.byte 1\n')
    obj = work / f'{label}-unexpected.o'
    run('as', '--32', '-o', obj, source)
    result = subprocess.run([
        str(linker), '-m', 'elf_i386', '-T', str(SOURCE / 'ide-rom.ld'),
        '-o', str(work / f'{label}-unexpected.elf'), str(obj),
    ], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'IDE ROM contains unexpected allocated sections' in result.stderr


def check_llvm(work, clang, lld):
    obj, elf, raw, rom = (work / name for name in
                         ('llvm.o', 'llvm.elf', 'llvm.raw', 'llvm.rom'))
    run(clang, '--target=i386-none-elf', '-m32', '-c', '-x', 'assembler',
        SOURCE / 'ide-rom.S', '-o', obj)
    run(lld, '-m', 'elf_i386', '-T', SOURCE / 'ide-rom.ld', '-o', elf, obj)
    run('objcopy', '-O', 'binary', '-j', '.text', elf, raw)
    check_elf(elf, raw.read_bytes())
    run(sys.executable, SOURCE / 'seal.py', raw, rom)
    check_image(rom)
    check_unexpected_section(work, lld, 'llvm')
    print('IDE ROM: LLVM zero-based ELF layout and checksums verified')


def build_and_check(work):
    output = work / 'published'
    root = work / 'build'
    command = [
        'make', '-C', ROOT / 'roms', 'ide-option-rom',
        'SEABIOS_CROSS_PREFIX=', f'SEABIOS_BUILD_ROOT={root}',
        f'SEABIOS_OUTPUT_DIR={output}',
    ]
    run(*command)
    rom = output / 'ide-isa.rom'
    data = check_image(rom)
    check_elf(root / 'ide-optionrom' / 'ide.elf',
              (root / 'ide-optionrom' / 'ide.raw').read_bytes())
    check_unexpected_section(work, 'ld', 'gnu')
    object_file = root / 'ide-optionrom' / 'ide.o'
    timestamps = (rom.stat().st_mtime_ns, object_file.stat().st_mtime_ns)
    run(*command)
    assert timestamps == (rom.stat().st_mtime_ns, object_file.stat().st_mtime_ns)

    broken = work / 'broken.raw'
    raw = bytearray((root / 'ide-optionrom' / 'ide.raw').read_bytes())
    raw[0] = 0
    broken.write_bytes(raw)
    bad = subprocess.run([sys.executable, SOURCE / 'seal.py', broken, rom],
                         capture_output=True)
    assert bad.returncode != 0
    assert rom.read_bytes() == data, 'failed seal modified published ROM'

    makefile = (ROOT / 'roms' / 'Makefile').read_text()
    assert 'bios: ide-option-rom build-seabios-config-seabios-128k' in makefile
    meson = (ROOT / 'pc-bios' / 'meson.build').read_text()
    assert "'bios-microvm.bin', 'ide-isa.rom'" in meson
    builder = (ROOT / 'scripts' / 'meson-build-seabios.bash').read_text()
    assert 'expected=(bios.bin bios-256k.bin bios-microvm.bin ide-isa.rom)' in builder
    print(f'IDE ROM: {len(data)} bytes, valid headers/checksums, incremental build verified')
    return rom


def guest_test(work, qemu, bios, rom):
    obj, elf, boot = (work / name for name in ('boot.o', 'boot.elf', 'boot.bin'))
    run('as', '--32', '-o', obj, SOURCE / 'tests' / 'boot-test.S')
    run('ld', '-m', 'elf_i386', '-Ttext=0x7c00', '-e', '_start', '-o', elf, obj)
    run('objcopy', '-O', 'binary', '-j', '.text', elf, boot)
    sector = boot.read_bytes()
    assert len(sector) == 512 and sector[-2:] == b'\x55\xaa'
    disk = work / 'disk.raw'
    disk.write_bytes((sector + b'\x5a' * 512 + b'\xa5' * 512).ljust(2 * 1024 * 1024, b'\0'))
    initial = disk.read_bytes()
    result = subprocess.run([
        qemu, '-machine', 'isapc', '-m', '16', '-nodefaults',
        '-display', 'none', '-serial', 'none', '-monitor', 'none',
        '-no-reboot', '-boot', 'order=c,menu=off',
        '-bios', str(bios), '-option-rom', str(rom),
        '-drive', f'file={disk},if=ide,index=0,format=raw,snapshot=on',
        '-device', 'isa-debug-exit,iobase=0xf4,iosize=0x04',
    ], timeout=45, capture_output=True, text=True)
    assert result.returncode == 33, (
        f'IDE boot test returned {result.returncode}; '
        f'expected 33 (geometry/read/data/write/invalid failures: 35/37/39/41/43)\n'
        f'{result.stdout}\n{result.stderr}')
    assert disk.read_bytes() == initial
    print('IDE ROM guest: CHS geometry, two-sector read, write rejection and error status verified')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bios', type=pathlib.Path)
    parser.add_argument('--qemu')
    parser.add_argument('--clang')
    parser.add_argument('--lld')
    args = parser.parse_args()
    if bool(args.bios) != bool(args.qemu):
        parser.error('--bios and --qemu must be supplied together')
    if bool(args.clang) != bool(args.lld):
        parser.error('--clang and --lld must be supplied together')
    with tempfile.TemporaryDirectory(prefix='whp-ide-rom-test-') as directory:
        work = pathlib.Path(directory)
        rom = build_and_check(work)
        if args.clang:
            check_llvm(work, args.clang, args.lld)
        if args.bios:
            guest_test(work, args.qemu, args.bios.resolve(), rom)


if __name__ == '__main__':
    main()
