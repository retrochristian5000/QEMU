#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

meson = (ROOT / "meson.build").read_text(encoding="utf-8")
meson_options = (ROOT / "meson_options.txt").read_text(encoding="utf-8")
prepare = (ROOT / "scripts/whp-build/prepare-build.bash").read_text(encoding="utf-8")
portable = (ROOT / "scripts/whp-build/portable-build.py").read_text(encoding="utf-8")
build_targets = (ROOT / "scripts/whp-build/build-targets.bash").read_text(encoding="utf-8")
config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
module_c = (ROOT / "util/module.c").read_text(encoding="utf-8")
module_h = (ROOT / "include/qemu/module.h").read_text(encoding="utf-8")
audio = (ROOT / "audio/meson.build").read_text(encoding="utf-8")
ui = (ROOT / "ui/meson.build").read_text(encoding="utf-8")
block = (ROOT / "block/meson.build").read_text(encoding="utf-8")
usb = (ROOT / "hw/usb/meson.build").read_text(encoding="utf-8")
display = (ROOT / "hw/display/meson.build").read_text(encoding="utf-8")
coreaudio = (ROOT / "audio/coreaudio.m").read_text(encoding="utf-8")

# Preserve upstream's conservative global default. WHP policy chooses modules
# at the build-adapter layer instead of silently changing every QEMU build.
assert "option('modules', type : 'feature', value : 'disabled'" in meson_options
assert "option('hvf', type: 'feature', value: 'disabled'" in meson_options
assert 'QEMU_HOST_MODULES="${QEMU_HOST_MODULES:-auto}"' in prepare
assert "QEMU_HOST_MODULES" in config
assert "Dynamic QEMU modules" in config

# WHP macOS auto mode should opt in to QEMU's existing DSO architecture.
assert '[[ "$HOST_OS" == Darwin && "$QEMU_HOST_MODULES" == auto ]]' in prepare
assert 'configure_args+=(--enable-modules)' in prepare
assert 'whp_add_optional_configure_switch "$QEMU_HOST_MODULES" modules' in prepare
assert "platform.system() == 'Darwin' and values['QEMU_HOST_MODULES'] == 'auto'" in portable
assert "configure_args.append('--enable-modules')" in portable
assert "optional_switch(configure_args, values['QEMU_HOST_MODULES'], 'modules')" in portable

# WHP macOS builds are TCG-only. Keep both host hypervisor accelerators out of
# the configure identity so future native-architecture targets cannot silently
# acquire KVM/HVF code or Hypervisor.framework signing entitlements.
assert 'configure_args+=(--disable-kvm --disable-hvf)' in prepare
assert "configure_args.extend(['--disable-kvm', '--disable-hvf'])" in portable

# Targeted builds must carry Meson's module alias when it exists. Otherwise a
# successful qemu-system-* link can leave its optional DSOs unbuilt.
for token in (
    'grep -Eq \'^build modules(:|[[:space:]])\' "$BUILD_DIR/build.ninja"',
    'build_target_list+=(modules)',
):
    assert token in build_targets, f"missing targeted module build contract: {token}"
for token in (
    "def dynamic_modules_enabled(",
    "def append_module_build_target(",
    "append_unique(requested_targets, 'modules')",
):
    assert token in portable, f"missing portable module build contract: {token}"

# Modules must remain incompatible with a fully static executable. Do not
# paper over this QEMU invariant by forcing both policies at once.
assert ".require(not get_option('prefer_static')" in meson
assert "Modules are incompatible with static linking" in meson

# Verify the DSO path is real rather than merely a collection of static
# archives. Meson stages PIC objects in .a files, then emits shared modules.
for token in (
    "sl = static_library(d + '-' + m",
    "pic: true",
    "emulator_modules += shared_module(sl.name()",
    "objects: sl.extract_all_objects(recursive: false)",
    "install_dir: qemu_moddir",
):
    assert token in meson, f"missing QEMU module build contract: {token}"

# Darwin modules are .dylib files and are loaded through GLib/GModule. The
# build stamp prevents accidentally mixing modules from different QEMU builds.
assert "host_dsosuf = '.dylib'" in meson
assert "g_module = g_module_open(fname, flags);" in module_c
assert "G_MODULE_BIND_LOCAL" in module_c
assert "DSO_STAMP_FUN_STR" in module_c
assert "#ifdef BUILD_DSO" in module_h

# The first migration set consists only of subsystems QEMU already declares as
# modules. These are optional host/backend boundaries rather than TCG/QOM core.
for token, text in (
    ("['coreaudio', coreaudio, files('coreaudio.m')]", audio),
    ("ui_modules += {'opengl' : opengl_ss}", ui),
    ("[curl, 'curl', files('curl.c')]", block),
    ("hw_usb_modules += {'host': usbhost_ss}", usb),
    ("hw_display_modules += {'virtio-gpu': virtio_gpu_ss}", display),
):
    assert token in text, f"expected module-safe subsystem disappeared: {token}"

assert "module_obj(TYPE_AUDIO_COREAUDIO);" in coreaudio

# Keep the hot Apple display path inside the emulator for now. AppleGFX and
# Cocoa were optimized as one tightly coupled Metal path; moving them behind a
# DSO boundary before measurement would add a new ABI/relocation variable.
assert "system_ss.add(when: cocoa, if_true: files('cocoa.m', 'cocoa-metal.m'))" in ui
assert "system_ss.add(when: [pvg, 'CONFIG_MAC_PVG_PCI']" in display
assert "system_ss.add(when: [pvg, 'CONFIG_MAC_PVG_MMIO']" in display

# The build tree has a relocated install bundle, so DSOs remain discoverable
# before a user performs a real installation.
assert "scripts/symlink-install-tree.py" in meson

print("macOS dynamic QEMU module policy audit passed")
