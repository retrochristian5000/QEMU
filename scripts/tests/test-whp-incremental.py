#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import platform
import subprocess
import tempfile
import unittest
from contextlib import contextmanager

ROOT = pathlib.Path(__file__).resolve().parents[2]
PORTABLE_BUILD_TOOL = ROOT / 'scripts' / 'whp-build' / 'portable-build.py'
MACOS_HYGIENE = ROOT / 'scripts' / 'macos-build-hygiene.bash'


def load_portable_build():
    spec = importlib.util.spec_from_file_location('whp_portable_build', PORTABLE_BUILD_TOOL)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@contextmanager
def temporary_environment(updates):
    old = os.environ.copy()
    try:
        os.environ.clear()
        os.environ.update(old)
        os.environ.update(updates)
        yield
    finally:
        os.environ.clear()
        os.environ.update(old)


def configured_targets(configure_args):
    for arg in configure_args:
        if arg.startswith('--target-list='):
            value = arg.split('=', 1)[1]
            return {target for target in value.split(',') if target}
    return set()


def configured_target_value(configure_args):
    for arg in configure_args:
        if arg.startswith('--target-list='):
            return arg.split('=', 1)[1]
    return ''


class WhpIncrementalTests(unittest.TestCase):
    def test_portable_explicit_target_overrides_disabled_saved_output_for_run(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td, temporary_environment({
            'BUILD_DIR': td,
            'BUILD_QEMU_IMG': '0',
            'BUILD_QEMU_SYSTEM_I386': '0',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_OPENBIOS': 'n',
            'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
            'WHP_INCREMENTAL_BUILD': '1',
        }):
            _, _, configure_args, _, _ = mod.build_plan(['qemu-system-ppc'])
        self.assertEqual(configured_targets(configure_args), {'ppc-softmmu'})

    def test_portable_explicit_qemu_img_enables_tools_for_run(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td, temporary_environment({
            'BUILD_DIR': td,
            'BUILD_QEMU_IMG': '0',
            'BUILD_QEMU_SYSTEM_I386': '0',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_OPENBIOS': 'n',
            'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
            'WHP_INCREMENTAL_BUILD': '1',
        }):
            _, _, configure_args, _, _ = mod.build_plan(['qemu-img'])
        self.assertIn('--enable-tools', configure_args)
        self.assertNotIn('--disable-tools', configure_args)

    def test_portable_incremental_target_expansion_preserves_previous_targets(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            (build_dir / '.whp-config').write_text(
                'SCHEMA=1\nQEMU_TARGET_LIST=i386-softmmu\n',
                encoding='utf-8',
            )
            with temporary_environment({
                'BUILD_DIR': td,
                'BUILD_QEMU_IMG': '0',
                'BUILD_QEMU_SYSTEM_I386': '0',
                'BUILD_QEMU_SYSTEM_PPC': '1',
                'BUILD_OPENBIOS': 'n',
                'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
                'WHP_INCREMENTAL_BUILD': '1',
            }):
                _, _, configure_args, _, _ = mod.build_plan(['qemu-system-ppc'])
        self.assertEqual(
            configured_targets(configure_args),
            {'i386-softmmu', 'ppc-softmmu'},
        )

    def test_portable_incremental_target_order_stays_previous_first(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            (build_dir / '.whp-config').write_text(
                'SCHEMA=2\nQEMU_TARGET_LIST=i386-softmmu,ppc-softmmu\n',
                encoding='utf-8',
            )
            with temporary_environment({
                'BUILD_DIR': td,
                'BUILD_QEMU_IMG': '0',
                'BUILD_QEMU_SYSTEM_I386': '0',
                'BUILD_QEMU_SYSTEM_PPC': '1',
                'BUILD_OPENBIOS': 'n',
                'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
                'WHP_INCREMENTAL_BUILD': '1',
            }):
                _, _, configure_args, _, _ = mod.build_plan(['qemu-system-ppc'])
        self.assertEqual(
            configured_target_value(configure_args),
            'i386-softmmu,ppc-softmmu',
        )

    def test_portable_relative_build_dir_is_source_relative(self):
        mod = load_portable_build()
        with temporary_environment({
            'BUILD_DIR': 'out/relative-build',
            'BUILD_QEMU_IMG': '0',
            'BUILD_QEMU_SYSTEM_I386': '0',
            'BUILD_QEMU_SYSTEM_PPC': '0',
            'BUILD_OPENBIOS': 'n',
            'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
        }):
            build_dir, _, _, _, _ = mod.build_plan(['qemu-img'])
        self.assertEqual(build_dir, ROOT / 'out' / 'relative-build')

    def test_portable_default_build_dir_is_host_scoped_and_runner_neutral(self):
        mod = load_portable_build()
        old_build_dir = os.environ.pop('BUILD_DIR', None)
        try:
            with temporary_environment({
                'BUILD_QEMU_IMG': '0',
                'BUILD_QEMU_SYSTEM_I386': '0',
                'BUILD_QEMU_SYSTEM_PPC': '0',
                'BUILD_OPENBIOS': 'n',
                'BOOTSTRAP_POWERPC_TOOLCHAIN': 'n',
            }):
                os.environ.pop('BUILD_DIR', None)
                build_dir, _, _, _, _ = mod.build_plan(['qemu-img'])
        finally:
            if old_build_dir is not None:
                os.environ['BUILD_DIR'] = old_build_dir
        name = build_dir.name
        self.assertNotIn('portable', name)
        self.assertNotIn('ppc', name)
        self.assertIn(mod.canonical_host_arch(platform.machine()), name)
        self.assertIn(mod.canonical_host_os(platform.system()), name)

    def test_macos_hygiene_never_recursively_deletes_build_dir(self):
        content = MACOS_HYGIENE.read_text(encoding='utf-8')
        self.assertNotIn('rm -rf "$BUILD_DIR"', content)

    def test_portable_owner_accepts_transferred_checkout_and_retains_profile(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            (build_dir / '.whp-build-owner').write_text(
                'SCHEMA=2\\nSOURCE_DIR=/old/computer/QEMU\\nHOST_TAG='
                + mod.host_build_tag() + '\\n',
                encoding='utf-8',
            )
            profile = build_dir / 'default.profdata'
            profile.write_bytes(b'old-profile')
            mod.validate_build_tree_owner(build_dir)
            mod.write_build_tree_owner(build_dir)
            self.assertEqual(profile.read_bytes(), b'old-profile')
            owner = (build_dir / '.whp-build-owner').read_text(encoding='utf-8')
            self.assertIn(f'PROJECT_ID={mod.PROJECT_ID}', owner)
            self.assertIn(f'SOURCE_DIR={mod.ROOT}', owner)

    def test_pre_pgo_tree_with_previous_source_is_adopted(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            (build_dir / '.whp-config').write_text(
                'SCHEMA=1\\nSOURCE_DIR=/old/computer/QEMU\\n'
                f'HOST_TAG={mod.host_build_tag()}\\n'
                'QEMU_TARGET_LIST=ppc-softmmu\\n',
                encoding='utf-8',
            )
            data = build_dir / 'default.profdata'
            data.write_bytes(b'pgodata')
            mod.validate_build_tree_owner(build_dir)
            mod.write_build_tree_owner(build_dir)
            self.assertEqual(data.read_bytes(), b'pgodata')

    def test_foreign_project_and_incompatible_host_are_rejected(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            owner = build_dir / '.whp-build-owner'
            owner.write_text(
                'SCHEMA=3\\nPROJECT_ID=foreign/QEMU\\n'
                f'SOURCE_DIR={mod.ROOT}\\nHOST_TAG={mod.host_build_tag()}\\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(RuntimeError, 'belongs to project'):
                mod.validate_build_tree_owner(build_dir)
            owner.write_text(
                'SCHEMA=2\\nSOURCE_DIR=/old/computer/QEMU\\n'
                'HOST_TAG=incompatible-host\\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(RuntimeError, 'host ABI'):
                mod.validate_build_tree_owner(build_dir)

    def test_unknown_host_from_transferred_custom_dir_stays_unowned(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            build_dir = pathlib.Path(td)
            (build_dir / '.whp-config').write_text(
                'SCHEMA=1\\nSOURCE_DIR=/old/computer/QEMU\\n'
                'QEMU_TARGET_LIST=ppc-softmmu\\n',
                encoding='utf-8',
            )
            with self.assertRaisesRegex(RuntimeError, 'non-empty unowned'):
                mod.validate_build_tree_owner(build_dir)

    def test_bash_configure_delegates_owner_migration_to_portable_helper(self):
        source = (ROOT / 'scripts/whp-build/configure.bash').read_text(encoding='utf-8')
        self.assertIn('"$SOURCE_DIR/scripts/whp-build/portable-build.py"', source)
        self.assertIn('--claim-build-dir', source)

    def test_entry_claims_build_directory_before_compiled_dependencies(self):
        launcher = (ROOT / 'build.sh').read_text(encoding='utf-8')
        claim = launcher.index('--claim-build-dir')
        libraries = launcher.index('. "$SOURCE_DIR/scripts/whp-build/host-libraries.sh"')
        native_llvm = launcher.index('if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then')
        self.assertLess(claim, libraries)
        self.assertLess(claim, native_llvm)
        self.assertIn('WHP_PORTABLE_PROBE_ONLY:-0', launcher)

    def test_claim_bootstrap_only_directory_preserves_pgo_data(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            mod.ROOT = pathlib.Path(td) / 'source'
            build_dir = mod.ROOT / 'build' / ('whp-' + mod.host_build_tag())
            (build_dir / 'bootstrap' / 'libtool').mkdir(parents=True)
            (build_dir / 'deps' / 'libisofs').mkdir(parents=True)
            (build_dir / 'pgo-raw').mkdir()
            raw = build_dir / 'pgo-raw' / 'profile.profraw'
            raw.write_bytes(b'profile-data')
            mod.validate_build_tree_owner(build_dir)
            mod.write_build_tree_owner(build_dir)
            self.assertEqual(raw.read_bytes(), b'profile-data')
            self.assertIn(
                f'SOURCE_DIR={mod.ROOT}',
                (build_dir / '.whp-build-owner').read_text(encoding='utf-8')
            )
            mod.validate_build_tree_owner(build_dir)

    def test_bootstrap_adoption_rejects_unrelated_and_wrong_arch(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            mod.ROOT = pathlib.Path(td) / 'source'
            build_dir = mod.ROOT / 'build' / ('whp-' + mod.host_build_tag())
            build_dir.mkdir(parents=True)
            (build_dir / 'not-qemu.txt').write_text('do not modify', encoding='utf-8')
            with self.assertRaisesRegex(RuntimeError, 'non-empty unowned BUILD_DIR'):
                mod.validate_build_tree_owner(build_dir)
            self.assertFalse((build_dir / '.whp-build-owner').exists())
            (build_dir / 'not-qemu.txt').unlink()
            (build_dir / 'bootstrap' / 'libtool').mkdir(parents=True)
            other = mod.ROOT / 'build' / 'whp-other-abi'
            other.mkdir()
            (other / 'bootstrap' / 'libtool').mkdir(parents=True)
            with self.assertRaisesRegex(RuntimeError, 'non-empty unowned BUILD_DIR'):
                mod.validate_build_tree_owner(other)

    def test_legacy_macos_identity_can_be_adopted_without_clean(self):
        mod = load_portable_build()
        with tempfile.TemporaryDirectory() as td:
            mod.ROOT = pathlib.Path(td) / 'source'
            build_dir = pathlib.Path(td) / 'existing'
            build_dir.mkdir()
            identity = build_dir / '.whp-macos-build-identity'
            identity.write_text(
                f'SOURCE_DIR={mod.ROOT}\nHOST_TAG={mod.host_build_tag()}\n',
                encoding='utf-8',
            )
            (build_dir / 'default.profdata').write_bytes(b'indexed')
            mod.validate_build_tree_owner(build_dir)
            mod.write_build_tree_owner(build_dir)
            self.assertEqual((build_dir / 'default.profdata').read_bytes(), b'indexed')

    def test_qemu_configure_reconfigures_existing_meson_without_wiping(self):
        script = (ROOT / 'configure').read_text(encoding='utf-8')
        self.assertIn('if test -f meson-private/coredata.dat; then', script)
        self.assertIn('meson_reconfigure=--reconfigure', script)
        self.assertIn('eval run_meson $meson_reconfigure $meson_options', script)
        self.assertNotIn('rm -rf meson-private meson-info meson-logs', script)

    def test_bash_explicit_target_expands_configured_target_list(self):
        script = r'''
set -euo pipefail
SOURCE_DIR="$1"
BUILD_DIR="$2"
HOME="$3"
source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SOURCE_DIR/scripts/whp-build/prepare-build.bash"
BUILD_QEMU_IMG=0
BUILD_QEMU_SYSTEM_I386=0
BUILD_QEMU_SYSTEM_PPC=0
BUILD_OPENBIOS=0
BOOTSTRAP_POWERPC_TOOLCHAIN=0
WHP_INCREMENTAL_BUILD=1
PREFIX="$BUILD_DIR/install"
whp_prepare_build qemu-system-ppc
printf '%s\n' "$QEMU_TARGET_LIST"
'''
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            build_dir = root / 'build'
            home = root / 'home'
            build_dir.mkdir()
            home.mkdir()
            result = subprocess.run(
                ['bash', '-c', script, 'bash', str(ROOT), str(build_dir), str(home)],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertEqual(
            {target for target in result.stdout.strip().split(',') if target},
            {'ppc-softmmu'},
        )

    def test_bash_explicit_qemu_img_enables_tools_for_run(self):
        script = r'''
set -euo pipefail
SOURCE_DIR="$1"
BUILD_DIR="$2"
HOME="$3"
source "$SOURCE_DIR/scripts/whp-build/common.bash"
source "$SOURCE_DIR/scripts/whp-build/prepare-build.bash"
BUILD_QEMU_IMG=0
BUILD_QEMU_SYSTEM_I386=0
BUILD_QEMU_SYSTEM_PPC=0
BUILD_OPENBIOS=0
BOOTSTRAP_POWERPC_TOOLCHAIN=0
WHP_INCREMENTAL_BUILD=1
PREFIX="$BUILD_DIR/install"
whp_prepare_build qemu-img
printf '%s\n' "$BUILD_QEMU_IMG"
'''
        with tempfile.TemporaryDirectory() as td:
            root = pathlib.Path(td)
            build_dir = root / 'build'
            home = root / 'home'
            build_dir.mkdir()
            home.mkdir()
            result = subprocess.run(
                ['bash', '-c', script, 'bash', str(ROOT), str(build_dir), str(home)],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertEqual(result.stdout.strip(), '1')

    def test_bash_incremental_reconfigure_unions_existing_target_set(self):
        script = r'''
set -euo pipefail
SOURCE_DIR="$1"
BUILD_DIR="$2"
mkdir -p "$SOURCE_DIR/configs/devices/ppc-softmmu" "$BUILD_DIR"
printf 'CONFIG_MAC_NEWWORLD=y\nCONFIG_MAC_OLDWORLD=y\n' > \
    "$SOURCE_DIR/configs/devices/ppc-softmmu/default.mak"
cat > "$SOURCE_DIR/configure" <<'EOF'
#!/bin/sh
printf '%s\n' "$@" > configure-args.txt
touch build.ninja
EOF
chmod +x "$SOURCE_DIR/configure"
printf 'SCHEMA=1\nSOURCE_DIR=%s\nQEMU_TARGET_LIST=i386-softmmu\n' \
    "$SOURCE_DIR" > "$BUILD_DIR/.whp-config"
HOST_OS=Linux
PROCESS_ARCH=x86_64
PHYSICAL_ARCH=x86_64
HOST_ARCH=x86_64
ROSETTA_TRANSLATED=0
MACOS_ALLOW_ROSETTA=0
MACOS_VERIFY_TOOLCHAIN=0
MACOS_ALLOW_NONCLANG=0
MACOS_ALLOW_COMPILER_CONFIG=0
MACOS_COMPILER_MANIFEST=disabled
MACOS_COMPILER_MANIFEST_SIGNATURE=disabled
MACOS_LTO_MANIFEST=disabled
MACOS_LTO_MANIFEST_SIGNATURE=disabled
CC_FOR_BUILD=cc
CXX_FOR_BUILD=c++
OBJC_FOR_BUILD=cc
STRIP_FOR_BUILD=strip
PKG_CONFIG_FOR_BUILD=pkg-config
CFLAGS=
MAKE_CMD=make
NINJA_CMD=ninja
QEMU_HOST_LTO=auto
BUILD_OPENBIOS=0
OPENBIOS_CROSS_COMPILE=
BOOTSTRAP_POWERPC_TOOLCHAIN=0
POWERPC_TOOLCHAIN_DIR="$BUILD_DIR/powerpc"
CONFIG_MAC_NEWWORLD=y
CONFIG_MAC_OLDWORLD=y
QEMU_TARGET_LIST=ppc-softmmu
WHP_INCREMENTAL_BUILD=1
configure_args=(--target-list=ppc-softmmu)
source "$3/scripts/whp-build/configure.bash"
whp_configure_build
cat "$BUILD_DIR/configure-args.txt"
'''
        with tempfile.TemporaryDirectory() as td:
            temp = pathlib.Path(td)
            source = temp / 'source'
            build = temp / 'build'
            result = subprocess.run(
                ['bash', '-c', script, 'bash', str(source), str(build), str(ROOT)],
                text=True,
                capture_output=True,
                check=True,
            )
        target_arg = next(
            line for line in result.stdout.splitlines()
            if line.startswith('--target-list=')
        )
        self.assertEqual(
            {target for target in target_arg.split('=', 1)[1].split(',') if target},
            {'i386-softmmu', 'ppc-softmmu'},
        )

    def test_bash_incremental_target_order_stays_previous_first(self):
        script = r'''
set -euo pipefail
BUILD_DIR="$1"
mkdir -p "$BUILD_DIR"
printf 'QEMU_TARGET_LIST=i386-softmmu,ppc-softmmu\n' > "$BUILD_DIR/.whp-config"
QEMU_TARGET_LIST=ppc-softmmu
WHP_INCREMENTAL_BUILD=1
configure_args=(--target-list=ppc-softmmu)
source "$2/scripts/whp-build/configure.bash"
whp_configure_merge_previous_targets "$BUILD_DIR/.whp-config"
whp_configure_sync_target_args
printf '%s\n' "$QEMU_TARGET_LIST"
'''
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                ['bash', '-c', script, 'bash', td, str(ROOT)],
                text=True,
                capture_output=True,
                check=True,
            )
        self.assertEqual(result.stdout.strip(), 'i386-softmmu,ppc-softmmu')


if __name__ == '__main__':
    unittest.main()
