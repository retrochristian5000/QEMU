#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / 'build.ps1'
DOC = ROOT / 'docs' / 'devel' / 'whp-build-orchestration.rst'

entry = ENTRY.read_text(encoding='utf-8')
doc = DOC.read_text(encoding='utf-8')

required = (
    '#requires -Version 5.1',
    'WHP_WINDOWS_BASH',
    'CYGWIN*|MINGW*|MSYS*',
    'cygpath -u',
    'WHP_BUILD_BASH',
    'WHP_SOURCE_UPDATE',
    'BUILD_SEABIOS_GRUB',
    'BUILD_SEABIOS_HYBRID_ISO',
    'GRUB_I386_BOOTSTRAP',
    'CHERE_INVOKING',
    'winsymlinks:native',
    '--noprofile',
    '--norc',
    'build.sh',
    "Write-Output 'WHP SeaBIOS UEFI lane: enabled'",
    'Write-Output "WHP Windows Bash:',
)
for token in required:
    assert token in entry, f'missing PowerShell launcher contract token: {token}'

assert 'Write-Host' not in entry, 'launcher status must stay capturable by CI pipelines'
assert '.ToArray()' not in entry, 'PowerShell 5.1 launcher must not rely on LINQ extension methods'
assert 'portable-build-entry.py' not in entry, (
    'PowerShell launcher must enter build.sh so firmware and QEMU share one policy path'
)
assert 'WSL Bash is intentionally not' in entry
assert '.\\build.ps1 qemu-system-i386' in doc
assert '.\\build.ps1 -SeaBIOSUefi qemu-system-i386' in doc
assert 'GRUB_X86_64_' in doc

print('PowerShell QEMU/SeaBIOS build entry contract: verified')
