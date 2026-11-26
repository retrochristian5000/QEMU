#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise a deterministic real-mode guest with the one-insn TB policies."""

import argparse
import pathlib
import subprocess
import tempfile


# xor ax,ax; mov cx,4096; inc ax; loop inc; cmp ax,4096;
# jne failure; mov al,0x10; out 0xf4,al; hlt;
# failure: mov al,0x11; out 0xf4,al; hlt
PROGRAM = bytes.fromhex(
    '31 c0 b9 00 10 40 e2 fd 3d 00 10 75 05 b0 10 e6 f4 f4 '
    'b0 11 e6 f4 f4'
)
RESET = bytes.fromhex('ea 00 00 00 f0')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('qemu', type=pathlib.Path,
                        help='path to the built qemu-system-i386 or x86_64')
    args = parser.parse_args()
    qemu = args.qemu.resolve(strict=True)
    with tempfile.TemporaryDirectory(prefix='whp-one-insn-tb-') as directory:
        bios = pathlib.Path(directory) / 'test.bin'
        rom = bytearray(65536)
        rom[:len(PROGRAM)] = PROGRAM
        rom[-16:-16 + len(RESET)] = RESET
        bios.write_bytes(rom)
        for name, accel, options in (
            ('baseline', 'tcg,thread=single', []),
            ('one-insn', 'tcg,thread=single,one-insn-per-tb=on', []),
            ('chained', 'tcg,thread=single,one-insn-per-tb=on,'
                        'one-insn-per-tb-chain=on', []),
            ('nochain', 'tcg,thread=single,one-insn-per-tb=on,'
                        'one-insn-per-tb-chain=on', ['-d', 'nochain']),
            ('icount', 'tcg,thread=single,one-insn-per-tb=on,'
                       'one-insn-per-tb-chain=on', ['-icount', 'shift=0']),
        ):
            result = subprocess.run(
                [str(qemu), '-machine', 'pc', '-accel', accel,
                 '-m', '16M', '-nodefaults', '-display', 'none',
                 '-serial', 'none', '-monitor', 'none',
                 '-bios', str(bios), '-device',
                 'isa-debug-exit,iobase=0xf4,iosize=4', *options],
                capture_output=True, text=True, timeout=30, check=False)
            # isa-debug-exit returns (value << 1) | 1.
            if result.returncode != 33:
                raise RuntimeError(
                    f'{name}: expected guest success exit 33, got '
                    f'{result.returncode}\n{result.stdout}\n{result.stderr}')
            print(f'{name}: guest instruction result verified')


if __name__ == '__main__':
    main()
