#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify optional Mach-O LLD flags are accepted by both Clang driver lanes."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / 'scripts/macos-builder.bash'
source = BUILDER.read_text(encoding='utf-8')
start = source.index('whp_native_lld_accepts_read_workers()\n{')
end = source.index('\n}\n', start) + len('\n}\n')
function = source[start:end]

with tempfile.TemporaryDirectory(prefix='whp-cxx-lld-flags-') as temp:
    directory = Path(temp)
    log = directory / 'calls.txt'
    for name in ('fake-c', 'fake-cxx'):
        executable = directory / name
        executable.write_text("""#!/bin/sh
printf '%s %s\\n' "$0" "$*" >> "$WHP_DRIVER_LOG"
case " $* " in
  *' -arch arm64e '*) ;;
  *) exit 2 ;;
esac
case " $* " in
  *' -isysroot /fake/MacOSX.sdk '*) ;;
  *) exit 3 ;;
esac
case " $* " in
  *' -mmacosx-version-min=15.0 '*) ;;
  *) exit 4 ;;
esac
case " $* " in
  *' -fuse-ld=lld '*) ;;
  *) exit 5 ;;
esac
case " $* " in
  *' -Wl,--read-workers=4 '*) ;;
  *) exit 6 ;;
esac
case "$0:$*" in
  *fake-cxx*' -x c++ '*) ;;
  *fake-c*' -x c '*) ;;
  *) exit 7 ;;
esac
if [ "$WHP_REJECT_CXX" = 1 ]; then
    case "$0" in *fake-cxx) exit 8 ;; esac
fi
exit 0
""", encoding='utf-8')
        executable.chmod(0o755)

    script = '\n'.join([
        'set -e',
        f'CC="{directory / "fake-c"}"',
        f'CXX="{directory / "fake-cxx"}"',
        'WHP_MACOS_ARCH=arm64e',
        'SDKROOT=/fake/MacOSX.sdk',
        'MACOSX_DEPLOYMENT_TARGET=15.0',
        function,
        'whp_native_lld_accepts_read_workers 4',
    ])
    common = {**os.environ, 'WHP_DRIVER_LOG': str(log)}
    accepted = subprocess.run(['bash', '-c', script],
                              env={**common, 'WHP_REJECT_CXX': '0'},
                              capture_output=True, text=True, check=False)
    assert accepted.returncode == 0, accepted.stderr
    lines = log.read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2, lines
    assert 'fake-c ' in lines[0]
    assert 'fake-cxx ' in lines[1]

    log.unlink()
    rejected = subprocess.run(['bash', '-c', script],
                              env={**common, 'WHP_REJECT_CXX': '1'},
                              capture_output=True, text=True, check=False)
    assert rejected.returncode != 0, 'Clang++ rejection must disable LLD workers'
    assert len(log.read_text(encoding='utf-8').splitlines()) == 2

print('Mach-O LLD Clang++ flag probes: verified')
