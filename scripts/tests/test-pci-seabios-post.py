#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Boot the pinned SeaBIOS and check Cirrus BAR placement after POST."""

import argparse
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time


MIB = 1024 * 1024
RAM = 64 * MIB
PCI_END = 0xfec00000
MARKER = b'Z'


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def qmp(stream, command):
    stream.write(json.dumps({'execute': command}).encode() + b'\n')
    stream.flush()
    while True:
        line = stream.readline()
        require(line, f'QMP disconnected during {command}')
        response = json.loads(line)
        if 'event' in response:
            continue
        require('return' in response, f'{command}: {response}')
        return response['return']


def devices(busses):
    for bus in busses:
        for device in bus['devices']:
            yield device
            bridge = device.get('pci_bridge', {})
            if 'devices' in bridge:
                yield from devices([bridge])


def check_regions(busses, aperture):
    cards = list(devices(busses))
    matches = [card for card in cards if card['qdev_id'] == 'cirrus']
    require(len(matches) == 1, 'expected exactly one Cirrus VGA device')
    card = matches[0]
    require(card['id']['vendor'] == 0x1013
            and card['id']['device'] == 0x00b8, 'incorrect Cirrus PCI ID')
    bars = {region['bar']: region for region in card['regions']}
    require(0 in bars and bars[0]['size'] == aperture,
            'incorrect Cirrus BAR0 aperture size')
    required_bars = (0, 1) if aperture == 32 * MIB else (0,)
    for index in required_bars:
        require(index in bars, f'missing Cirrus BAR{index}')
        region = bars[index]
        if index == 1:
            require(region['size'] == 4096, 'incorrect Cirrus MMIO BAR size')
        start, size = region['address'], region['size']
        end = start + size
        require(region['type'] == 'memory' and size > 0
                and (size & (size - 1)) == 0
                and start >= RAM and start % size == 0 and end <= PCI_END,
                f'invalid Cirrus BAR{index}: {region}')
        for other in cards:
            for candidate in other['regions']:
                if other is card and candidate['bar'] == index:
                    continue
                if candidate['type'] != 'memory' or candidate['address'] < 0:
                    continue
                lo = candidate['address']
                hi = lo + candidate['size']
                require(end <= lo or start >= hi,
                        f'Cirrus BAR{index} overlaps {candidate}')


def run_case(qemu, bios, vga, machine, model, aperture):
    with tempfile.TemporaryDirectory(prefix='whp-pci-post-') as tmp:
        root = Path(tmp)
        image = root / 'boot.img'
        marker = root / 'boot.log'
        debug = root / 'bios.log'
        errors = root / 'qemu.log'
        sockpath = root / 'qmp.sock'
        # 16-bit boot sector: MOV DX,00E9h; MOV AL,'Z'; OUT DX,AL;
        # CLI; HLT; JMP HLT. A marker proves firmware reached INT 19h boot.
        sector = bytes.fromhex('ba e9 00 b0 5a ee fa f4 eb fd')
        with image.open('wb') as disk:
            disk.write(sector.ljust(510, b'\0') + b'\x55\xaa')
            disk.truncate(16 * MIB)
        command = [
            str(qemu), '-machine', machine, '-accel', 'tcg,thread=single',
            '-m', '64M', '-nodefaults', '-display', 'none',
            '-monitor', 'none', '-serial', 'none',
            '-bios', str(bios), '-boot', 'order=c,menu=off',
            '-drive', f'file={image},format=raw,if=ide',
            '-device', f'{model},id=cirrus,pci-legacy-decode=on,romfile={vga}',
            '-chardev', f'file,id=boot,path={marker}',
            '-device', 'isa-debugcon,iobase=0xe9,chardev=boot',
            '-chardev', f'file,id=bioslog,path={debug}',
            '-device', 'isa-debugcon,iobase=0x402,chardev=bioslog',
            '-qmp', f'unix:{sockpath},server=on,wait=off',
        ]
        with errors.open('wb') as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL,
                                    stderr=stderr)
            try:
                deadline = time.monotonic() + 30
                with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                    conn.settimeout(10)
                    while True:
                        require(proc.poll() is None, 'QEMU exited before QMP')
                        try:
                            conn.connect(str(sockpath))
                            break
                        except (FileNotFoundError, ConnectionRefusedError):
                            require(time.monotonic() < deadline, 'QMP startup timeout')
                            time.sleep(0.05)
                    with conn.makefile('rwb') as stream:
                        greeting = json.loads(stream.readline())
                        require('QMP' in greeting, 'invalid QMP greeting')
                        qmp(stream, 'qmp_capabilities')
                        while not marker.exists() or MARKER not in marker.read_bytes():
                            require(proc.poll() is None, 'QEMU exited during firmware POST')
                            require(time.monotonic() < deadline, 'SeaBIOS boot marker timeout')
                            time.sleep(0.05)
                        check_regions(qmp(stream, 'query-pci'), aperture)
                        qmp(stream, 'quit')
                require(proc.wait(timeout=10) == 0, 'QEMU exited abnormally')
            except Exception as error:
                for log in (debug, errors):
                    if log.exists():
                        print(f'--- {log.name} ---')
                        print(log.read_bytes()[-16384:].decode(errors='replace'))
                raise RuntimeError(f'{machine}/{model}: {error}') from error
            finally:
                if proc.poll() is None:
                    proc.kill()
                    proc.wait(timeout=10)
    print(f'{machine}/{model}: SeaBIOS boot and PCI resources passed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--bios', type=Path, required=True)
    parser.add_argument('--vgabios', type=Path, required=True)
    args = parser.parse_args()
    qemu, bios, vga = (p.resolve(strict=True)
                       for p in (args.qemu, args.bios, args.vgabios))
    require(bios.stat().st_size == 256 * 1024, 'expected a 256 KiB SeaBIOS')
    require(vga.stat().st_size > 0, 'empty SeaVGABIOS')
    for machine in ('pc', 'pc-i440bx', 'q35'):
        for model, aperture in (('gd5446a-pci', 16 * MIB),
                                ('gd5446b-pci', 32 * MIB)):
            run_case(qemu, bios, vga, machine, model, aperture)


if __name__ == '__main__':
    main()
