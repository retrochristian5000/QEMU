#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import hashlib
import importlib.util
import os
import pathlib
import platform
import shlex
import shutil
import subprocess
import sys
import tempfile
from typing import Dict, List, Tuple

ROOT = pathlib.Path(__file__).resolve().parents[2]
CONFIG_TOOL = ROOT / 'scripts' / 'whp-config' / 'config.py'
USER_CONFIG = ROOT / '.whpconfig'


def load_config_module():
    spec = importlib.util.spec_from_file_location('whp_config', CONFIG_TOOL)
    if spec is None or spec.loader is None:
        raise RuntimeError(f'cannot load WHP configuration tool: {CONFIG_TOOL}')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def normalize_bool(name: str, value: str) -> str:
    lowered = value.lower()
    if lowered in ('1', 'y', 'yes', 'true', 'on'):
        return 'y'
    if lowered in ('0', 'n', 'no', 'false', 'off'):
        return 'n'
    raise ValueError(f'{name} must be y/n or 1/0')


def normalize_choice(name: str, value: str, choices: Tuple[str, ...]) -> str:
    lowered = value.lower()
    if lowered == 'auto' and 'auto' in choices:
        return 'auto'
    if lowered in ('1', 'y', 'yes', 'true', 'on') and 'y' in choices:
        return 'y'
    if lowered in ('0', 'n', 'no', 'false', 'off') and 'n' in choices:
        return 'n'
    if value in choices:
        return value
    raise ValueError(f"{name} must be one of: {', '.join(choices)}")


def resolved_values() -> Dict[str, str]:
    mod = load_config_module()
    state = mod.load_config(USER_CONFIG)
    values = dict(state.values)
    for option in mod.OPTIONS:
        raw = os.environ.get(option.key)
        if raw is None:
            continue
        if option.kind == 'bool':
            values[option.key] = normalize_bool(option.key, raw)
        elif option.kind == 'choice':
            values[option.key] = normalize_choice(option.key, raw, option.choices)
        else:
            mod.validate_value(option, raw)
            values[option.key] = raw
    return values


def _safe_tag(value: str) -> str:
    cleaned = ''.join(
        character.lower() if character.isalnum() or character in '._-' else '-'
        for character in value
    )
    while '--' in cleaned:
        cleaned = cleaned.replace('--', '-')
    return cleaned.strip('-') or 'unknown'


def canonical_host_arch(value: str | None = None) -> str:
    machine = (value or platform.machine() or 'unknown').lower()
    if machine in ('amd64', 'x86_64'):
        return 'x86_64'
    if machine in ('aarch64', 'arm64'):
        return 'arm64'
    return _safe_tag(machine)


def canonical_host_os(value: str | None = None) -> str:
    system = (value or platform.system() or 'unknown').lower()
    if system == 'darwin':
        return 'apple-darwin'
    if system == 'windows' or system.startswith(('mingw', 'msys', 'cygwin')):
        return 'windows'
    return _safe_tag(system)


def host_build_tag() -> str:
    return f'{canonical_host_arch()}-{canonical_host_os()}'


def _source_build_root_writable() -> bool:
    build_root = ROOT / 'build'
    if build_root.exists():
        return build_root.is_dir() and os.access(build_root, os.W_OK)
    return os.access(ROOT, os.W_OK)


def _portable_cache_root() -> pathlib.Path:
    xdg_cache = os.environ.get('XDG_CACHE_HOME')
    if xdg_cache:
        return pathlib.Path(xdg_cache).expanduser()
    home = os.environ.get('HOME')
    if home:
        return pathlib.Path(home).expanduser() / '.cache'
    return pathlib.Path(tempfile.gettempdir())


def default_build_dir() -> pathlib.Path:
    leaf = f'whp-{host_build_tag()}'
    if _source_build_root_writable():
        return ROOT / 'build' / leaf

    source_key = hashlib.sha256(str(ROOT).encode('utf-8')).hexdigest()[:12]
    return _portable_cache_root() / 'whp-qemu' / 'builds' / source_key / leaf


def resolve_build_dir() -> pathlib.Path:
    requested = os.environ.get('BUILD_DIR')
    if not requested:
        return default_build_dir()
    build_dir = pathlib.Path(requested).expanduser()
    if not build_dir.is_absolute():
        build_dir = ROOT / build_dir
    return build_dir


def default_prefix(build_dir: pathlib.Path) -> pathlib.Path:
    home = os.environ.get('HOME')
    if home:
        home_path = pathlib.Path(home).expanduser()
        if home_path.is_dir() and os.access(home_path, os.W_OK):
            return home_path / '.local' / 'whp-qemu'
    return build_dir / 'install'


def optional_switch(args: List[str], value: str, feature: str) -> None:
    if value == 'y':
        args.append(f'--enable-{feature}')
    elif value == 'n':
        args.append(f'--disable-{feature}')


def select_runner() -> List[str]:
    requested_ninja = os.environ.get('NINJA_CMD') or os.environ.get('NINJA')
    if requested_ninja:
        return shlex.split(requested_ninja)
    for name in ('ninja', 'ninja-build'):
        path = shutil.which(name)
        if path:
            return [path]

    requested_make = os.environ.get('MAKE_CMD') or os.environ.get('MAKE')
    if requested_make:
        return shlex.split(requested_make)
    for name in ('gmake', 'make'):
        path = shutil.which(name)
        if path:
            return [path]
    raise RuntimeError('neither Ninja nor Make is available to run the QEMU build')


def append_unique(values: List[str], value: str) -> None:
    if value and value not in values:
        values.append(value)


def requested_system_targets(argv: List[str]) -> List[str]:
    targets: List[str] = []
    for requested in argv:
        if not requested.startswith('qemu-system-'):
            continue
        arch = requested[len('qemu-system-'):]
        if arch:
            append_unique(targets, f'{arch}-softmmu')
    return targets


def previous_configured_targets(build_dir: pathlib.Path) -> List[str]:
    config_file = build_dir / '.whp-config'
    if not config_file.is_file():
        return []

    try:
        lines = config_file.read_text(encoding='utf-8').splitlines()
    except OSError:
        return []

    for line in lines:
        if line.startswith('QEMU_TARGET_LIST='):
            return [
                target for target in line.split('=', 1)[1].split(',')
                if target
            ]

    # Build trees created before the dedicated target field can still be
    # expanded without a reset.  Recover the target list from the old recorded
    # configure command when possible.
    for line in lines:
        if not line.startswith('CONFIGURE_ARG='):
            continue
        for arg in line.split('=', 1)[1].split():
            if arg.startswith('--target-list='):
                return [
                    target for target in arg.split('=', 1)[1].split(',')
                    if target
                ]
    return []


def _metadata(path: pathlib.Path) -> Dict[str, str]:
    values: Dict[str, str] = {}
    try:
        lines = path.read_text(encoding='utf-8').splitlines()
    except OSError:
        return values
    for line in lines:
        if '=' not in line:
            continue
        key, value = line.split('=', 1)
        values[key] = value
    return values


def validate_build_tree_owner(build_dir: pathlib.Path) -> None:
    if not build_dir.exists():
        return
    try:
        has_files = next(build_dir.iterdir(), None) is not None
    except OSError as exc:
        raise RuntimeError(f'cannot inspect build directory {build_dir}: {exc}') from exc
    if not has_files:
        return

    expected_source = str(ROOT)
    expected_tag = host_build_tag()
    owner_file = build_dir / '.whp-build-owner'
    owner = _metadata(owner_file)
    if owner:
        if owner.get('SOURCE_DIR') != expected_source:
            raise RuntimeError(
                f'BUILD_DIR belongs to another QEMU source tree: {build_dir}'
            )
        recorded_tag = owner.get('HOST_TAG')
        if recorded_tag and recorded_tag != expected_tag:
            raise RuntimeError(
                f'BUILD_DIR belongs to host ABI {recorded_tag}, not {expected_tag}: '
                f'{build_dir}'
            )
        return

    # Adopt build trees produced by older WHP revisions when their existing
    # configuration proves source-tree ownership.  Missing host metadata is
    # tolerated once so old incremental work is not discarded.
    config = _metadata(build_dir / '.whp-config')
    if config.get('SOURCE_DIR') == expected_source:
        recorded_arch = config.get('HOST_ARCH')
        recorded_os = config.get('HOST_OS')
        if recorded_arch and recorded_os:
            recorded_tag = f'{canonical_host_arch(recorded_arch)}-{canonical_host_os(recorded_os)}'
            if recorded_tag != expected_tag:
                raise RuntimeError(
                    f'BUILD_DIR belongs to host ABI {recorded_tag}, not {expected_tag}: '
                    f'{build_dir}'
                )
        return

    raise RuntimeError(
        f'refusing to use non-empty unowned BUILD_DIR: {build_dir}'
    )


def write_build_tree_owner(build_dir: pathlib.Path) -> None:
    owner_file = build_dir / '.whp-build-owner'
    candidate = owner_file.with_name(owner_file.name + '.new')
    with candidate.open('w', encoding='utf-8') as handle:
        handle.write('SCHEMA=2\n')
        handle.write(f'SOURCE_DIR={ROOT}\n')
        handle.write(f'HOST_TAG={host_build_tag()}\n')
    os.replace(candidate, owner_file)


def write_portable_config(
    build_dir: pathlib.Path,
    prefix: pathlib.Path,
    configure_args: List[str],
) -> None:
    target_list = ''
    for arg in configure_args:
        if arg.startswith('--target-list='):
            target_list = arg.split('=', 1)[1]
            break

    config_file = build_dir / '.whp-config'
    candidate = config_file.with_name(config_file.name + '.new')
    with candidate.open('w', encoding='utf-8') as handle:
        handle.write('SCHEMA=2\n')
        handle.write('PORTABLE_CORE=1\n')
        handle.write(f'SOURCE_DIR={ROOT}\n')
        handle.write(f'HOST_OS={canonical_host_os()}\n')
        handle.write(f'HOST_ARCH={canonical_host_arch()}\n')
        handle.write(f'PREFIX={prefix}\n')
        handle.write(f'QEMU_TARGET_LIST={target_list}\n')
        handle.write(f'CONFIGURE_ARG={" ".join(configure_args)}\n')
    os.replace(candidate, config_file)


def build_plan(argv: List[str]) -> Tuple[pathlib.Path, pathlib.Path, List[str], List[str], List[str]]:
    values = resolved_values()
    build_dir = resolve_build_dir()
    prefix_value = values['PREFIX']
    prefix = default_prefix(build_dir) if prefix_value == 'auto' else pathlib.Path(prefix_value).expanduser()

    selected_targets: List[str] = []
    if values['BUILD_QEMU_SYSTEM_PPC'] == 'y':
        append_unique(selected_targets, 'ppc-softmmu')
    if values['BUILD_QEMU_SYSTEM_I386'] == 'y':
        append_unique(selected_targets, 'i386-softmmu')
    for target in requested_system_targets(argv):
        append_unique(selected_targets, target)

    targets: List[str] = []
    if values['WHP_INCREMENTAL_BUILD'] == 'y':
        for target in previous_configured_targets(build_dir):
            append_unique(targets, target)
    for target in selected_targets:
        append_unique(targets, target)

    configure_args: List[str] = [f'--prefix={prefix}']
    if targets:
        configure_args.append(f"--target-list={','.join(targets)}")
    else:
        configure_args.append('--disable-system')

    tools_enabled = values['BUILD_QEMU_IMG'] == 'y' or 'qemu-img' in argv
    configure_args.append('--enable-tools' if tools_enabled else '--disable-tools')
    optional_switch(configure_args, values['QEMU_HOST_LTO'], 'lto')
    optional_switch(configure_args, values['MACOS_ENABLE_GTK'], 'gtk')
    optional_switch(configure_args, values['MACOS_ENABLE_PA'], 'pa')

    if platform.system() == 'Darwin':
        optional_switch(configure_args, values['MACOS_ENABLE_COCOA'], 'cocoa')
        optional_switch(configure_args, values['MACOS_ENABLE_COREAUDIO'], 'coreaudio')

    custom_macs = values['CONFIG_MAC_NEWWORLD'] != 'y' or values['CONFIG_MAC_OLDWORLD'] != 'y'
    if custom_macs:
        raise RuntimeError(
            'custom PowerPC Mac device filtering requires the Bash feature adapter; '
            'core QEMU remains buildable with the tracked PPC defaults'
        )

    declines: List[str] = []
    if values['BUILD_OPENBIOS'] == 'y':
        raise RuntimeError(
            'OpenBIOS was explicitly requested, but the portable core does not run '
            'the Bash firmware adapter'
        )
    if values['BOOTSTRAP_POWERPC_TOOLCHAIN'] == 'y':
        raise RuntimeError(
            'PowerPC toolchain bootstrap was explicitly requested, but the portable '
            'core does not run the Bash firmware adapter'
        )
    if values['BUILD_OPENBIOS'] == 'auto' and 'ppc-softmmu' in targets:
        declines.append('OpenBIOS:auto:firmware-adapter-unavailable')

    requested_targets = argv[:] if argv else ['all']
    return build_dir, prefix, configure_args, requested_targets, declines


def print_plan(build_dir: pathlib.Path, prefix: pathlib.Path, configure_args: List[str], targets: List[str], declines: List[str]) -> None:
    print(f'BUILD_DIR={build_dir}')
    print(f'PREFIX={prefix}')
    for arg in configure_args:
        print(f'CONFIGURE_ARG={arg}')
    for target in targets:
        print(f'BUILD_TARGET={target}')
    for decline in declines:
        print(f'OPTIONAL_DECLINE={decline}')


def locate_built_binary(build_dir: pathlib.Path, name: str) -> pathlib.Path:
    for candidate in (build_dir / name, build_dir / f'{name}.exe'):
        if candidate.is_file():
            return candidate
    raise RuntimeError(f'expected build artifact was not produced: {name}')


def verify_requested_outputs(build_dir: pathlib.Path, requested_targets: List[str]) -> Dict[str, pathlib.Path]:
    artifacts: Dict[str, pathlib.Path] = {}
    if 'all' in requested_targets:
        return artifacts

    for target in requested_targets:
        if target != 'qemu-img' and not target.startswith('qemu-system-'):
            continue
        binary = locate_built_binary(build_dir, target)
        version = subprocess.run(
            [str(binary), '--version'],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if version.returncode != 0:
            raise RuntimeError(f'built artifact failed its version probe: {binary}')
        artifacts[target] = binary

        if target == 'qemu-system-ppc':
            machines = subprocess.run(
                [str(binary), '-machine', 'help'],
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                check=False,
            )
            if machines.returncode != 0:
                raise RuntimeError(f'PowerPC emulator failed machine-list probe: {binary}')
            for machine in ('powermac3_1', 'mac99'):
                if machine not in machines.stdout:
                    raise RuntimeError(
                        f'PowerPC emulator lost required machine profile {machine}: {binary}'
                    )
    return artifacts


def main(argv: List[str]) -> int:
    if sys.version_info < (3, 9):
        print('error: Python 3.9 or newer is required by QEMU', file=sys.stderr)
        return 2

    if argv == ['--print-build-dir']:
        print(resolve_build_dir())
        return 0

    try:
        build_dir, prefix, configure_args, requested_targets, declines = build_plan(argv)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 2

    if os.environ.get('WHP_PORTABLE_PROBE_ONLY') == '1':
        print_plan(build_dir, prefix, configure_args, requested_targets, declines)
        return 0

    for decline in declines:
        print(f'WHP optional feature skipped: {decline}', file=sys.stderr)

    build_dir.mkdir(parents=True, exist_ok=True)
    artifacts: Dict[str, pathlib.Path] = {}
    try:
        validate_build_tree_owner(build_dir)
        write_build_tree_owner(build_dir)
        subprocess.run([str(ROOT / 'configure'), *configure_args], cwd=build_dir, check=True)
        write_portable_config(build_dir, prefix, configure_args)

        runner = select_runner()
        jobs = os.environ.get('JOBS') or str(os.cpu_count() or 1)
        runner_name = pathlib.Path(runner[0]).name
        if runner_name.startswith('ninja'):
            build_command = [*runner, '-C', str(build_dir), '-j', jobs, *requested_targets]
        else:
            build_command = [*runner, '-C', str(build_dir), f'-j{jobs}', *requested_targets]
        subprocess.run(build_command, check=True)

        values = resolved_values()
        if values['INSTALL'] == 'y':
            subprocess.run([*runner, '-C', str(build_dir), 'install'], check=True)

        artifacts = verify_requested_outputs(build_dir, requested_targets)
    except (OSError, subprocess.CalledProcessError, RuntimeError) as exc:
        print(f'error: core QEMU build failed: {exc}', file=sys.stderr)
        return 1

    manifest = build_dir / '.whp-build-artifacts'
    with manifest.open('w', encoding='utf-8') as handle:
        handle.write('SCHEMA=2\n')
        handle.write('PORTABLE_CORE=1\n')
        handle.write(f'SOURCE_DIR={ROOT}\n')
        handle.write(f'BUILD_DIR={build_dir}\n')
        handle.write(f'PREFIX={prefix}\n')
        handle.write(f'REQUESTED_TARGETS={" ".join(requested_targets)}\n')
        for target, path in artifacts.items():
            handle.write(f'ARTIFACT={target}:{path}\n')
        if 'qemu-system-ppc' in artifacts:
            handle.write('POWERMAC3_1_REGISTERED=yes\n')
            handle.write('MAC99_REGISTERED=yes\n')
        for decline in declines:
            handle.write(f'OPTIONAL_DECLINE={decline}\n')
    print(f'build artifact manifest: {manifest}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
