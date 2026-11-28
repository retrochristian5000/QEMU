#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Bootstrap the pinned WHP sccacher fork for local compiler caching."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))
from bootstrap_env import clean_host_environment, reconcile_submodule
SUBMODULE = pathlib.Path('toolchains/sccacher')
SCHEMA = 8
MINIMUM_RUST = (1, 91, 0)


def call(argv, *, cwd=None, env=None, capture=False):
    process = subprocess.run(
        argv, cwd=cwd, env=env, text=True, check=False,
        stdout=subprocess.PIPE if capture else sys.stderr,
        stderr=subprocess.PIPE if capture else sys.stderr,
    )
    if process.returncode:
        detail = process.stderr.strip() if capture else ''
        raise RuntimeError(f'{argv[0]} failed ({process.returncode})' +
                           (f': {detail}' if detail else ''))
    return process.stdout.strip() if capture else ''


def pinned_source():
    source = ROOT / SUBMODULE
    # Use the Git selected by host-tools.sh, not an unrelated PATH fallback.
    # The parent bootstrap now schedules sccacher after Git promotion.
    git = os.environ.get('GIT') or os.environ.get('WHP_GIT_SEED')
    if not git:
        raise RuntimeError('sccacher requires a selected host Git (GIT or WHP_GIT_SEED)')
    revision = reconcile_submodule(ROOT, SUBMODULE, git=git)
    dirty = call([git, '-C', str(source), 'status', '--porcelain',
                  '--untracked-files=no'], capture=True)
    if dirty:
        raise RuntimeError('sccacher submodule has uncommitted changes; refusing build')
    if not (source / 'Cargo.toml').is_file() or not (source / 'Cargo.lock').is_file():
        raise RuntimeError('sccacher source must contain Cargo.toml and Cargo.lock')
    return source, revision


def build_jobs(environ):
    raw = environ.get('WHP_SCCACHE_BUILD_JOBS', '2')
    if not re.fullmatch(r'[1-9][0-9]*', raw):
        raise ValueError('WHP_SCCACHE_BUILD_JOBS must be a positive integer')
    return int(raw)


def cargo_environment(environ, target, *, rustc=None):
    # Cargo's BLAKE3 and zstd dependencies compile native C code.
    env = clean_host_environment(environ)
    # Keep the locked zstd-sys bundled C provider. Presence of this
    # variable can select pkg-config, even when its value is empty.
    env.pop('ZSTD_SYS_USE_PKG_CONFIG', None)
    env.pop('CRATE_CC_NO_DEFAULTS', None)
    # Cargo build scripts (including cc-rs) can read target-qualified compiler
    # and flag overrides. A parent's QEMU C++/preprocessor options must never
    # become flags for the native C/C++ code compiled while building sccache.
    # Keep the validated build-machine tool identity, not target selections.
    for key in tuple(env):
        # Native tool identities are distinct from target-qualified overrides.
        if key in ('CC_FOR_BUILD', 'CXX_FOR_BUILD', 'CPP_FOR_BUILD'):
            continue
        # Cargo profile and bootstrap overrides can silently change native
        # Rust/C dependencies without changing the locked source revision.
        # Restore only the intentionally selected profile values below.
        if key.startswith('CARGO_PROFILE_') or key == 'RUSTC_BOOTSTRAP':
            env.pop(key, None)
            continue
        if (key.startswith(('CC_', 'CXX_', 'CPP_', 'CFLAGS_', 'CXXFLAGS_',
                            'CPPFLAGS_', 'HOST_CC_', 'HOST_CXX_', 'HOST_CPP_',
                            'HOST_CFLAGS_', 'HOST_CXXFLAGS_', 'HOST_CPPFLAGS_',
                            'AR_', 'ARFLAGS_', 'RANLIB_', 'HOST_AR_',
                            'HOST_ARFLAGS_', 'HOST_RANLIB_', 'PKG_CONFIG_',
                            'CARGO_TARGET_'))
                or key in ('TARGET_CC', 'TARGET_CXX', 'TARGET_CPP',
                           'TARGET_CFLAGS', 'TARGET_CXXFLAGS', 'TARGET_CPPFLAGS',
                           'HOST_CFLAGS', 'HOST_CXXFLAGS', 'HOST_CPPFLAGS',
                           'HOST_AR', 'HOST_ARFLAGS', 'HOST_RANLIB',
                           'TARGET_ARFLAGS', 'TARGET_PKG_CONFIG', 'HOST_PKG_CONFIG',
                           'CARGO_BUILD_TARGET', 'CARGO_BUILD_RUSTC',
                           'CARGO_BUILD_RUSTDOC', 'CARGO_BUILD_RUSTFLAGS',
                           'IPHONEOS_DEPLOYMENT_TARGET',
                           'IPHONESIMULATOR_DEPLOYMENT_TARGET',
                           'TVOS_DEPLOYMENT_TARGET',
                           'WATCHOS_DEPLOYMENT_TARGET',
                           'XROS_DEPLOYMENT_TARGET',
                           'DRIVERKIT_DEPLOYMENT_TARGET',
                           'PLATFORM_NAME', 'EFFECTIVE_PLATFORM_NAME',
                           'SDK_NAME')):
            # Cargo target/linker/runner overrides can redirect a native
            # sccache build to a QEMU guest architecture. The build's
            # selected Cargo/Rust toolchain is supplied explicitly below.
            env.pop(key, None)
    cc = env.get('CC_FOR_BUILD')
    if not cc:
        raise RuntimeError('sccacher requires the validated CC_FOR_BUILD seed')
    env['CC'] = cc
    env['HOST_CC'] = cc
    # cc-rs also compiles C++ in some native Cargo dependencies. Never let it
    # independently rediscover a different compiler or target CXX on PATH.
    cxx = env.get('CXX_FOR_BUILD')
    if cxx:
        env['CXX'] = cxx
        env['HOST_CXX'] = cxx
    for key in ('RUSTC_WRAPPER', 'RUSTC_WORKSPACE_WRAPPER',
                'CARGO_BUILD_RUSTC_WRAPPER', 'CARGO_BUILD_RUSTC_WORKSPACE_WRAPPER',
                'RUSTFLAGS', 'CARGO_ENCODED_RUSTFLAGS',
                'RUSTDOCFLAGS', 'CARGO_ENCODED_RUSTDOCFLAGS'):
        env.pop(key, None)
    # Ignore inherited target Rust compiler selections; only the admitted
    # rustc seed may be passed to Cargo by ensure().
    env.pop('RUSTC', None)
    if rustc is not None:
        env['RUSTC'] = rustc
    env.update({
        'CARGO_TARGET_DIR': str(target),
        'CARGO_PROFILE_RELEASE_LTO': 'false',
        'CARGO_PROFILE_RELEASE_CODEGEN_UNITS': '8',
        'CARGO_PROFILE_RELEASE_DEBUG': '0',
        'CARGO_INCREMENTAL': '0',
    })
    return env


def native_producer_identity(environ):
    """Identify native C/C++ compilers and the SDK used by Cargo's C deps.

    The installed sccache binary is not an LLVM/QEMU target artifact, but
    bundled BLAKE3/zstd can use cc-rs. A Rust-only identity cannot safely
    reuse a binary after the native compiler or SDK changes.
    """
    cc = environ.get('CC_FOR_BUILD', '')
    cxx = environ.get('CXX_FOR_BUILD', '')
    if not cc or not cxx:
        raise RuntimeError(
            'sccacher identity requires validated CC_FOR_BUILD and CXX_FOR_BUILD'
        )

    def tool_version(path):
        lines = call([path, '--version'], capture=True).splitlines()
        if not lines or not lines[0]:
            raise RuntimeError(f'native compiler cannot report version: {path}')
        return lines[0]

    return {
        'cc': cc,
        'cc_version': tool_version(cc),
        'cxx': cxx,
        'cxx_version': tool_version(cxx),
        'sdkroot': environ.get('SDKROOT', ''),
        'deployment': environ.get('MACOSX_DEPLOYMENT_TARGET', ''),
        'developer_dir': environ.get('DEVELOPER_DIR', ''),
    }


def native_work_key(identity):
    """Keep Cargo's compiled C artifacts within one native producer lane.

    Source revisions still share the same lane so Cargo can rebuild changed
    crates incrementally. Compiler, SDK, Rust or profile changes select a
    separate work tree without deleting earlier build outputs.
    """
    inputs = {
        name: identity[name] for name in (
            'schema', 'native_producer', 'rustc_path', 'rustc',
            'cargo_path', 'cargo', 'profile', 'rust_target'
        )
    }
    return hashlib.sha256(
        json.dumps(inputs, sort_keys=True).encode('utf-8')
    ).hexdigest()[:16]


def require_tool_version(tool, banner):
    match = re.match(rf'^{re.escape(tool)} (\d+)\.(\d+)\.(\d+)(?:\s|$)', banner)
    if not match or tuple(map(int, match.groups())) < MINIMUM_RUST:
        minimum = '.'.join(map(str, MINIMUM_RUST))
        raise RuntimeError(f'sccacher requires {tool} {minimum} or newer: {banner}')


def host_tools():
    # Cargo is a pre-QEMU root capability, selected through the WHP seed.
    # Use /bin/sh explicitly so the seed also works from source archives
    # that did not preserve executable file modes.
    cargo = call(['/bin/sh', str(ROOT / 'seeds/cargo.sh'), '--print-seed'],
                 capture=True)
    rustc = call(['/bin/sh', str(ROOT / 'seeds/rustc.sh'), '--print-seed'],
                 capture=True)
    version = call([rustc, '--version'], capture=True)
    require_tool_version('rustc', version)
    cargo_version = call([cargo, '--version'], capture=True)
    require_tool_version('cargo', cargo_version)
    return cargo, rustc, version, cargo_version


def rust_host_target(rustc):
    banner = call([rustc, '--version', '--verbose'], capture=True)
    hosts = [line.removeprefix('host: ') for line in banner.splitlines()
             if line.startswith('host: ')]
    if len(hosts) != 1 or not re.fullmatch(r'[A-Za-z0-9_]+(?:-[A-Za-z0-9_]+)+', hosts[0]):
        raise RuntimeError('rustc did not report a valid native host target')
    return hosts[0]


def cargo_build_command(cargo, jobs, rust_target, *, offline=False):
    argv = [cargo, 'build', '--locked', '--release', '--no-default-features',
            '--bin', 'sccache', '--jobs', str(jobs), '--target', rust_target]
    if offline:
        argv.append('--offline')
    return argv


def ensure(build_dir, *, cargo_offline=False):
    source, revision = pinned_source()
    cargo, rustc, rust_version, cargo_version = host_tools()
    jobs = build_jobs(os.environ)
    rust_target = rust_host_target(rustc)
    host = f'{platform.system().lower()}-{platform.machine().lower()}'
    prefix = build_dir / 'toolchains' / 'sccache' / host
    executable = prefix / 'bin' / 'sccache'
    marker = prefix / '.whp-sccacher.json'
    identity = {'schema': SCHEMA, 'gitlink': revision,
                'rustc_path': rustc, 'rustc': rust_version,
                'cargo_path': cargo, 'cargo': cargo_version,
                'rust_target': rust_target,
                'features': 'local-only',
                'profile': 'lto=false,codegen-units=8,debug=0',
                'native_producer': native_producer_identity(os.environ)}
    if executable.is_file() and os.access(executable, os.X_OK) and marker.is_file():
        try:
            if json.loads(marker.read_text(encoding='utf-8')) == identity:
                call([str(executable), '--version'], capture=True)
                return executable
        except (ValueError, RuntimeError, OSError):
            pass
    # A stale Cargo target directory can preserve native C archives even if
    # the sccache executable marker rejects them. Partition compiled objects
    # by producer identity without discarding previous incremental work.
    target = (build_dir / 'toolchain-work' / 'sccacher' /
              f'{host}-v{SCHEMA}-{native_work_key(identity)}')
    target.mkdir(parents=True, exist_ok=True)
    print(f'WHP sccacher: building {revision} with {jobs} Cargo jobs', file=sys.stderr)
    call(cargo_build_command(cargo, jobs, rust_target, offline=cargo_offline),
         cwd=source, env=cargo_environment(os.environ, target, rustc=rustc))
    built = target / rust_target / 'release' / 'sccache'
    if not built.is_file():
        raise RuntimeError('Cargo succeeded without producing the sccache executable')
    call([str(built), '--version'], capture=True)
    (prefix / 'bin').mkdir(parents=True, exist_ok=True)
    # Atomic replacements: never delete the previously working cache binary.
    with tempfile.TemporaryDirectory(prefix='whp-sccacher-', dir=prefix) as staging:
        staged_bin = pathlib.Path(staging) / 'sccache'
        staged_marker = pathlib.Path(staging) / 'marker'
        shutil.copy2(built, staged_bin)
        staged_marker.write_text(json.dumps(identity, sort_keys=True) + '\n', encoding='utf-8')
        os.replace(staged_bin, executable)
        os.replace(staged_marker, marker)
    return executable


def verify_managed_executable(build_dir: pathlib.Path,
                              selected: pathlib.Path) -> bool:
    """Check the managed-cache provenance before enabling PCH consumer caching.

    This is a local build-policy guard, not a cryptographic attestation of
    executable bytes. Never infer the capability from a caller-set flag alone.
    """
    host = f'{platform.system().lower()}-{platform.machine().lower()}'
    prefix = build_dir.resolve() / 'toolchains' / 'sccache' / host
    executable = prefix / 'bin' / 'sccache'
    marker = prefix / '.whp-sccacher.json'
    try:
        if selected.resolve(strict=True) != executable.resolve(strict=True):
            return False
        if not executable.is_file() or not os.access(executable, os.X_OK):
            return False
        identity = json.loads(marker.read_text(encoding='utf-8'))
        if (identity.get('schema') != SCHEMA or
                identity.get('features') != 'local-only' or
                identity.get('profile') != 'lto=false,codegen-units=8,debug=0' or
                identity.get('native_producer') !=
                native_producer_identity(os.environ)):
            return False
        git = os.environ.get('GIT') or os.environ.get('WHP_GIT_SEED') or shutil.which('git')
        if not git:
            return False
        entry = call([git, '-C', str(ROOT), 'ls-tree', 'HEAD',
                      '--', str(SUBMODULE)], capture=True)
        match = re.fullmatch(
            r'160000 commit ([0-9a-f]{40})\ttoolchains/sccacher', entry
        )
        return match is not None and identity.get('gitlink') == match.group(1)
    except (OSError, ValueError, RuntimeError, AttributeError):
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build-dir', type=pathlib.Path, required=True)
    parser.add_argument('--cargo-offline', action='store_true',
                        help='use cached Cargo dependencies; Git source policy is separate')
    parser.add_argument('--verify-executable', type=pathlib.Path,
                        help='check an existing pinned local-only sccacher without rebuilding')
    args = parser.parse_args()
    if args.verify_executable is not None:
        return 0 if verify_managed_executable(
            args.build_dir, args.verify_executable
        ) else 1
    try:
        path = ensure(args.build_dir.resolve(), cargo_offline=args.cargo_offline)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f'error: WHP sccacher: {exc}', file=sys.stderr)
        return 1
    print(path)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
