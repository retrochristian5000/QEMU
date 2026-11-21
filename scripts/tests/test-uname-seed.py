#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Native uname seed contract, independent of LLVM and guest targets."""

from pathlib import Path
import os
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / 'seeds/uname.sh'
BRIDGE = ROOT / 'scripts/whp-build/seed-bin/uname'
BUILD = (ROOT / 'build.sh').read_text(encoding='utf-8')
NATIVE = (ROOT / 'scripts/bootstrap-native-clang.bash').read_text(encoding='utf-8')

for script in (SEED, BRIDGE):
    subprocess.run(['/bin/sh', '-n', str(script)], check=True)

assert 'WHP_UNAME_SEED=$("$SOURCE_DIR/seeds/uname.sh" --print-seed)' in BUILD
assert 'WHP_UNAME_LOCKED=1' in BUILD
assert BUILD.index('WHP_UNAME_LOCKED=1') < BUILD.index('WHP_HOST_KERNEL=$(uname -s')
assert 'WHP_UNAME_SEED=$("$SOURCE_DIR/seeds/uname.sh" --print-seed)' in NATIVE
assert 'host_kernel="$("$WHP_UNAME_SEED" -s)"' in NATIVE
assert 'host_arch="$("$WHP_UNAME_SEED" -m)"' in NATIVE
assert 'macos_upgrade_native_llvm_triple' in NATIVE

reference = next(
    (p for p in (Path('/usr/bin/uname'), Path('/bin/uname'))
     if p.is_file() and os.access(p, os.X_OK)), None,
)
assert reference is not None, 'native uname is required by this test'


def call(*args, env=None, executable=SEED):
    return subprocess.run(
        ['/bin/sh', str(executable), *args], env=env,
        capture_output=True, text=True,
    )


clean = os.environ.copy()
clean.pop('WHP_UNAME_SEED', None)
for option in ('-s', '-m', '-r', '-n', '-a'):
    expected = subprocess.run([str(reference), option], check=True,
                              capture_output=True, text=True)
    actual = call(option, env=clean)
    assert actual.returncode == 0, (option, actual.stderr)
    assert actual.stdout == expected.stdout, option
selected = call('--print-seed', env=clean)
assert selected.returncode == 0 and selected.stdout.strip() == str(reference)
assert call('--check', env=clean).returncode == 0
assert call('--whp-uname-adapter-probe', env=clean).stdout.strip() == (
    'whp-qemu-uname-seed-adapter'
)

with tempfile.TemporaryDirectory(prefix='whp-uname-seed-') as td:
    temp = Path(td)
    fake_uname = temp / 'uname'
    fake_uname.write_text(
        '#!/bin/sh\nprintf "PoisonedKernel\\n"\n', encoding='utf-8',
    )
    fake_uname.chmod(0o700)
    poisoned_path = clean | {'PATH': str(temp) + os.pathsep + clean.get('PATH', '')}
    assert call('-s', env=poisoned_path).stdout.strip() == (
        subprocess.check_output([str(reference), '-s'], text=True).strip()
    )

    for override in (str(fake_uname), str(SEED), str(temp / 'missing'),
                     'invalid uname argument'):
        candidate_env = poisoned_path | {'WHP_UNAME_SEED': override}
        bad = call('--print-seed', env=candidate_env)
        assert bad.returncode != 0, (override, bad.stdout, bad.stderr)

    bridge_path = str(BRIDGE.parent) + os.pathsep + poisoned_path['PATH']
    indirect = call('--print-seed', env=clean | {
        'PATH': bridge_path, 'WHP_UNAME_SEED': 'uname',
    })
    assert indirect.returncode != 0

    pinned_env = poisoned_path | {'WHP_UNAME_SEED': str(reference)}
    pinned = call('--print-seed', env=pinned_env)
    assert pinned.returncode == 0 and pinned.stdout.strip() == str(reference)

    # The bridge must not recursively select itself, and its locked mode
    # must ignore PATH poisoning while preserving the normal uname flags.
    unlocked_bridge = call('-s', env=poisoned_path, executable=BRIDGE)
    assert unlocked_bridge.returncode == 0
    assert unlocked_bridge.stdout == call('-s', env=clean).stdout
    locked = call('-m', env=pinned_env | {'WHP_UNAME_LOCKED': '1'},
                  executable=BRIDGE)
    assert locked.returncode == 0 and locked.stdout == call('-m', env=clean).stdout
    rejected = call('-s', env=clean | {'WHP_UNAME_LOCKED': '1'},
                    executable=BRIDGE)
    assert rejected.returncode != 0 and 'no usable seed' in rejected.stderr

print('native uname seed: verified')
