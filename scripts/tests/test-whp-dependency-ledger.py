#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]
GITMODULES = ROOT / ".gitmodules"
LEDGER = ROOT / "docs" / "devel" / "whp-dependency-ledger.rst"


def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(GITMODULES, encoding="utf-8")
    paths = [
        parser[section]["path"].strip()
        for section in parser.sections()
        if section.startswith("submodule ") and "path" in parser[section]
    ]

    ledger = LEDGER.read_text(encoding="utf-8")
    missing = [path for path in paths if f"``{path}``" not in ledger]
    if missing:
        raise SystemExit(
            "error: WHP dependency ledger is missing submodules: "
            + ", ".join(sorted(missing))
        )

    # The pinned Meson fork is the default; an explicitly saved venv
    # selection must remain authoritative without silent migration.
    meson_section = 'submodule "toolchains/meson"'
    if meson_section not in parser:
        raise SystemExit("error: WHP Meson source submodule is missing")
    meson = parser[meson_section]
    if (meson.get("path") != "toolchains/meson"
            or meson.get("url") != "https://github.com/retrochristian5000/Meson.git"
            or meson.get("branch") != "master"):
        raise SystemExit("error: WHP Meson submodule points to an unexpected source")

    required_contracts = {
        "pinned Meson source boundary": (
            "Pinned Meson source boundary",
            "toolchains/meson",
            "toolchains/meson/meson.py",
            "WHP_MESON_PROVIDER=venv",
            "never silently migrated",
        ),
        "Aften/JACK conditional edge": (
            "Full macOS server builds have a conditional Aften edge",
            "``--client-only`` profile deliberately skips Aften",
        ),
        "AArch64/arm64e distinction": (
            "``aarch64``",
            "``arm64e``",
            "NEON",
            "optimization opportunity",
        ),
        "circularity policy": (
            "Circularity guards",
            "must not make\n   itself its own root dependency",
        ),
        "gitlink authority": (
            "The gitlink recorded by the QEMU commit is authoritative",
        ),
        "external active-consumer classification": (
            "External host-tool edges by active consumer",
            "PowerPC GCC/binutils **source rebuild**",
            "Reusing a validated installed PowerPC toolchain",
            "OpenBIOS / SeaBIOS preparation",
            "IA32 EFI GRUB source/LLVM expansion",
            "macOS toolchain and LTO manifests",
            "Optional mold linker",
        ),
        "optional toolchain boundaries": (
            "Optional toolchain bootstrap requirements",
            "BOOTSTRAP_AUTOMAKE=auto",
            "Libtool/libtoolize",
            "sccache/sccacher",
            "CMake is checked after the cache miss",
            "Rust/Cargo identities",
        ),
        "required dependency guard policy": (
            "Required dependency guard policy",
            "not a second source of immutable commit gates",
            "Downstream",
            "Failure of an unrelated optional dependency must not stop",
            "Incomplete ancestry is",
        ),
    }
    for label, needles in required_contracts.items():
        for needle in needles:
            if needle not in ledger:
                raise SystemExit(
                    f"error: WHP dependency ledger lost {label}: {needle}"
                )

    # The PowerPC cross-toolchain can be reused without network/download,
    # archive, checksum or GNU Make prerequisites. These checks belong after
    # the installed-toolchain marker and capability check, not at entry.
    powerpc = (ROOT / "scripts" / "bootstrap-powerpc-toolchain.bash").read_text(
        encoding="utf-8"
    )
    cache_hit = powerpc.index('toolchain_is_usable "$TOOLCHAIN_DIR"')
    for needle in (
        'make_banner=$("$MAKE_CMD" --version',
        'for required in tar bzip2 gzip perl ln mv rm; do',
        'if command -v curl >/dev/null 2>&1; then',
        'if command -v shasum >/dev/null 2>&1; then',
    ):
        if needle not in powerpc or powerpc.index(needle) < cache_hit:
            raise SystemExit(
                "error: PowerPC rebuild-only prerequisite precedes cache reuse: "
                + needle
            )
    early_checks = powerpc[:cache_hit]
    if 'for required in tar bzip2 gzip perl' in early_checks:
        raise SystemExit("error: PowerPC source tools became universal roots")

    # Capability-first auto must not rebuild Automake/Autoconf merely
    # because the host is Darwin. Force modes still select their fork.
    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    for name, probe in (
        ("AUTOMAKE", "whp_automake_pair_usable"),
        ("AUTOCONF", "whp_autoconf_pair_usable"),
    ):
        start = host_tools.index("WHP_NEED_" + name + "=0")
        end = host_tools.index('if [ "$WHP_NEED_' + name + '" = 1 ]', start)
        segment = host_tools[start:end]
        if '"$WHP_HOST_OS" = macos' in segment:
            raise SystemExit(
                f"error: macOS auto forces managed {name} without a capability miss"
            )
        if f'if [ "$BOOTSTRAP_{name}" = 1 ]; then' not in segment:
            raise SystemExit(f"error: explicit {name} force mode was lost")
        if probe not in host_tools:
            raise SystemExit(f"error: missing host capability test for {name}")

    mold = (ROOT / "scripts/whp-build/prepare-mold.bash").read_text(
        encoding="utf-8"
    )
    cache_hit = mold.index('if [[ -x "$linker" && -f "$signature_file"')
    cmake_guard = mold.index('if ! command -v "$cmake_cmd"')
    if cmake_guard <= cache_hit:
        raise SystemExit("error: mold CMake check precedes installed cache reuse")

    # Keep the sccache marker anchored to the source and selected Rust/Cargo
    # pair; these checks determine whether a cached binary is still valid.
    sccache = (ROOT / "scripts/ensure-sccache.py").read_text(
        encoding="utf-8"
    )
    for field in ("'gitlink': revision", "'rustc_path': rustc",
                  "'cargo': cargo_version"):
        if field not in sccache:
            raise SystemExit("error: sccache lost cache identity: " + field)

    # Keep GLib build inputs, early GTK probes and Meson-native consumers
    # distinct; the GLib source fork is not an unconditional bootstrap stage.
    glib_section = 'submodule "toolchains/glib"'
    if glib_section not in parser:
        raise SystemExit("error: pinned GLib source is not registered")
    if (parser[glib_section].get("path") != "toolchains/glib"
            or parser[glib_section].get("url")
            != "https://github.com/retrochristian5000/Glib.git"):
        raise SystemExit("error: unexpected GLib source provider")

    meson_source = (ROOT / "meson.build").read_text(encoding="utf-8")
    hexagon_source = (ROOT / "target/hexagon/meson.build").read_text(
        encoding="utf-8"
    )
    gtk_env_source = (ROOT / "scripts/macos-gtk-environment.bash").read_text(
        encoding="utf-8"
    )
    gtk_verify_source = (ROOT / "scripts/verify-macos-gtk.bash").read_text(
        encoding="utf-8"
    )
    for label, contents, needles in (
        ("QEMU Meson", meson_source,
         ("glib_req_ver = '>=2.66.0'",
          "glib_pc = dependency('glib-2.0'",
          "gmodule-export-2.0", "gmodule-no-export-2.0")),
        ("Hexagon build machine", hexagon_source,
         ("hexagon_idef_parser",
          "find_program('flex')",
          "find_program('bison', version: '>=3.0')",
          "dependency('glib-2.0', native: true, static: false)")),
        ("early macOS GTK environment", gtk_env_source,
         ('"$pkg_config_executable" --exists gtk+-3.0',
          "PKG_CONFIG_PATH_FOR_BUILD")),
        ("early macOS GTK validation", gtk_verify_source,
         ("gtk+-3.0", "gtk-header-probe.c", "gtk_link_flags")),
    ):
        for needle in needles:
            if needle not in contents:
                raise SystemExit(
                    f"error: {label} GLib dependency edge changed: {needle}"
                )

    builder_source = (ROOT / "builder.bash").read_text(encoding="utf-8")
    gtk_position = builder_source.index(
        'if [[ "$HOST_OS" == Darwin && "$MACOS_ENABLE_GTK" == 1 ]]; then'
    )
    qemu_position = builder_source.index("whp_configure_build", gtk_position)
    if gtk_position >= qemu_position:
        raise SystemExit("error: macOS GTK preflight moved after QEMU configure")

    for needle in (
        "Pinned GLib bootstrap prerequisites and early consumers",
        "GLib 2.89.3", "Meson >= 1.4.0", "libffi >= 3.0.0",
        "PCRE2 >= 10.32", "GVDB", "MACOS_ENABLE_GTK=1",
        "native: true, static: false", "pyvenv",
    ):
        if needle not in ledger:
            raise SystemExit("error: GLib bootstrap ledger lost: " + needle)

    # Audit the QEMU-native graph at its owning source files, not via
    # additional global seed or bootstrap prerequisites.
    native_files = {
        "QEMU Meson": (
            ROOT / "meson.build",
            (
                "glib_req_ver = '>=2.66.0'",
                "dependency('glib-2.0'",
                "dependency('zlib', required: true)",
                "dependency('pixman-1'",
                "add_languages('objc', required: true",
                "find_program('gdbus-codegen'",
                "find_program('rustdoc'",
                "find_program('bindgen'",
                "bindgen.version().version_compare('<0.60.0')",
            ),
        ),
        "QEMU Python groups": (
            ROOT / "pythondeps.toml",
            ("[meson]", "[meson-rust]", "[tooling]", "[docs]", "[functests]"),
        ),
        "QEMU Rust minimum": (
            ROOT / "rust" / "Cargo.toml",
            ('rust-version = "1.83.0"',),
        ),
        "QEMU minimal CI package inventory": (
            ROOT / "tests" / "lcitool" / "projects" / "qemu-minimal.yml",
            (" - glib2", " - libffi", " - pixman", " - libfdt"),
        ),
    }
    for label, (source_file, probes) in native_files.items():
        source_text = source_file.read_text(encoding="utf-8")
        for probe in probes:
            if probe not in source_text:
                raise SystemExit(
                    f"error: {label} dependency contract changed: {probe}"
                )

    for probe in (
        "QEMU-native configure/Meson dependency cross-check",
        "GLib >= 2.66.0",
        "pixman >= 0.21.8",
        "Rust >= 1.83.0",
        "``bindgen`` >= 0.60.0",
        "``rustdoc``",
        "gdbus-codegen",
        "OBJC_FOR_BUILD",
        "WHP_MACOS_DEPENDENCY_PROVIDER",
    ):
        if probe not in ledger:
            raise SystemExit("error: QEMU-native graph ledger lost: " + probe)

    # Preserve the actual phase boundary in the single production owner.
    stage_script = (ROOT / "builder.bash").read_text(encoding="utf-8")
    stage_calls = (
        'whp_prepare_build "$@"',
        "whp_prepare_seabios_grub_sources",
        "whp_prepare_homebrew_pkg_config",
        "whp_configure_build",
        'whp_build_targets "$@"',
    )
    last_stage = -1
    for stage in stage_calls:
        position = stage_script.find(stage, last_stage + 1)
        if position < 0:
            raise SystemExit("error: QEMU build phase missing/reordered: " + stage)
        last_stage = position

    if len(paths) != len(set(paths)):
        raise SystemExit("error: duplicate submodule paths in .gitmodules")

    print(f"WHP dependency ledger: {len(paths)} top-level submodules covered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
