#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Execute the real PowerPC host-tool resolver without source downloads."""

from pathlib import Path
import os
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = (ROOT / "scripts/bootstrap-powerpc-toolchain.bash").read_text(
    encoding="utf-8"
)


def source_function(name: str) -> str:
    """Extract a top-level Bash function, not a copy of its selection policy."""
    start = SOURCE.index(f"{name}()\n{{\n")
    end = SOURCE.index("\n}\n", start) + 2
    return SOURCE[start:end]


# Exercise the exact GNU PowerPC build/host admission functions with the
# shared Apple-specific ABI parser. No macOS runner or source download is
# necessary to distinguish aliases from a real Canadian-cross request.
DARWIN_ABI_HELPERS = (ROOT / "scripts/whp-build/macos-target-abi.bash").read_text(
    encoding="utf-8"
)
TRIPLET_HELPERS = (
    "set -euo pipefail\n"
    + DARWIN_ABI_HELPERS + "\n"
    + source_function("toolchain_build_host_triplets_match") + "\n"
    + source_function("toolchain_darwin_build_matches_process") + "\n"
    + 'case "$1" in\n'
    + '  roles) toolchain_build_host_triplets_match "$2" "$3" "$4" ;;\n'
    + '  process) toolchain_darwin_build_matches_process "$2" "$3" ;;\n'
    + '  *) exit 2 ;;\n'
    + 'esac\n'
)


BASH_HELPERS = (
    "set -euo pipefail\n"
    + source_function("set_command") + "\n"
    + source_function("resolve_host_tool") + "\n"
    + "resolve_host_tool TOOLCHAIN_HOST_AR ar\n"
    + "resolve_host_tool TOOLCHAIN_HOST_RANLIB ranlib\n"
    + 'printf "%s\\n%s\\n" "$TOOLCHAIN_HOST_AR" "$TOOLCHAIN_HOST_RANLIB"\n'
)


class HostArchiveSelection(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-powerpc-ar-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.ar_build = self.executable("build-ar")
        self.ar_seed = self.executable("seed-ar")
        self.ar_explicit = self.executable("explicit-ar")
        self.ranlib_build = self.executable("build-ranlib")
        self.ranlib_seed = self.executable("seed-ranlib")
        self.ranlib_explicit = self.executable("explicit-ranlib")
        self.executable("ar")
        self.executable("ranlib")

    def executable(self, name):
        path = self.bin / name
        path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        path.chmod(0o755)
        return str(path)

    def run_selection(self, **values):
        env = os.environ.copy()
        for name in (
            "AR", "RANLIB", "AR_FOR_BUILD", "RANLIB_FOR_BUILD",
            "WHP_AR_SEED", "WHP_RANLIB_SEED", "TOOLCHAIN_HOST_AR",
            "TOOLCHAIN_HOST_RANLIB", "AR_FOR_TARGET", "RANLIB_FOR_TARGET",
        ):
            env.pop(name, None)
        env["PATH"] = str(self.bin) + os.pathsep + env.get("PATH", "/usr/bin:/bin")
        env.update(values)
        return subprocess.run(
            ["/bin/bash", "-c", BASH_HELPERS],
            env=env, capture_output=True, text=True, timeout=10, check=False,
        )

    def assert_selected(self, expected_ar, expected_ranlib, **overrides):
        result = self.run_selection(**overrides)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, expected_ar + "\n" + expected_ranlib + "\n")

    def test_inherits_existing_build_machine_pair(self):
        self.assert_selected(
            self.ar_build, self.ranlib_build,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
            AR=self.ar_explicit, RANLIB=self.ranlib_explicit,
            AR_FOR_TARGET=self.ar_explicit, RANLIB_FOR_TARGET=self.ranlib_explicit,
        )

    def test_seed_overrides_fallback_build_tools(self):
        self.assert_selected(
            self.ar_seed, self.ranlib_seed,
            WHP_AR_SEED=self.ar_seed, WHP_RANLIB_SEED=self.ranlib_seed,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
        )

    def test_explicit_toolchain_hosts_take_priority(self):
        self.assert_selected(
            self.ar_explicit, self.ranlib_explicit,
            TOOLCHAIN_HOST_AR=self.ar_explicit,
            TOOLCHAIN_HOST_RANLIB=self.ranlib_explicit,
            WHP_AR_SEED=self.ar_seed, WHP_RANLIB_SEED=self.ranlib_seed,
            AR_FOR_BUILD=self.ar_build, RANLIB_FOR_BUILD=self.ranlib_build,
        )

    def test_generic_discovery_only_if_no_host_role_is_defined(self):
        # Darwin intentionally discovers the active Xcode/CLT archive tools
        # through xcrun. Other hosts use generic PATH discovery instead.
        if sys.platform == "darwin":
            result = self.run_selection(
                AR=self.ar_explicit, RANLIB=self.ranlib_explicit,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            selected = result.stdout.splitlines()
            self.assertEqual(len(selected), 2)
            for program, path in zip(("ar", "ranlib"), selected):
                self.assertEqual(Path(path).name, program)
                self.assertTrue(Path(path).is_file())
                self.assertTrue(os.access(path, os.X_OK))
                self.assertNotEqual(path, str(self.bin / program))
        else:
            self.assert_selected(str(self.bin / "ar"), str(self.bin / "ranlib"),
                                 AR=self.ar_explicit, RANLIB=self.ranlib_explicit)

    def test_relative_tool_names_are_locked_to_absolute_paths(self):
        self.assert_selected(str(self.bin / "ar"), str(self.bin / "ranlib"),
                             AR_FOR_BUILD="ar", RANLIB_FOR_BUILD="ranlib")

    def test_invalid_explicit_selection_does_not_fall_back(self):
        result = self.run_selection(AR_FOR_BUILD=str(self.root / "missing-ar"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("command is not executable", result.stderr)
        result = self.run_selection(AR_FOR_BUILD=f"{self.ar_build} --bogus")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("must name one executable", result.stderr)

    def test_configure_inherits_selected_identity(self):
        self.assertIn('"AR=$TOOLCHAIN_HOST_AR"', SOURCE)
        self.assertIn('"AR_FOR_BUILD=$TOOLCHAIN_HOST_AR"', SOURCE)
        self.assertIn('"RANLIB=$TOOLCHAIN_HOST_RANLIB"', SOURCE)
        self.assertIn('"RANLIB_FOR_BUILD=$TOOLCHAIN_HOST_RANLIB"', SOURCE)
        self.assertIn("-u AR_FOR_TARGET", SOURCE)
        self.assertIn("-u RANLIB_FOR_TARGET", SOURCE)


class HostTripletAdmission(unittest.TestCase):
    def probe(self, *args):
        return subprocess.run(
            ["/bin/bash", "-c", TRIPLET_HELPERS, "--", *args],
            capture_output=True, text=True, timeout=10, check=False,
        )

    def test_equivalent_apple_darwin_and_macosx_native_hosts(self):
        # The original build/host strings remain different: only the
        # comparison key is normalized, so configure and cache retain intent.
        for build, host in (
            ("aarch64-apple-darwin24.6", "aarch64-apple-macosx15.6"),
            ("arm64-apple-darwin25.2.0", "aarch64-apple-macosx26.2"),
            ("arm64-apple-macosx27.2", "aarch64-apple-darwin27.2.0"),
            ("x86_64-apple-darwin22", "x86_64-apple-macosx13.0"),
            ("arm64e-apple-darwin27.2.0", "arm64e-apple-macosx27.2"),
        ):
            with self.subTest(build=build, host=host):
                result = self.probe("roles", build, host, "Darwin")
                self.assertEqual(result.returncode, 0, result.stderr)

    def test_genuine_canadian_cross_and_nonapple_darwin_rejected(self):
        for build, host, platform in (
            ("aarch64-apple-darwin24.6", "aarch64-apple-macosx15.7", "Darwin"),
            ("aarch64-apple-darwin24.6", "arm64e-apple-macosx15.6", "Darwin"),
            ("aarch64-apple-darwin24.6", "x86_64-apple-macosx15.6", "Darwin"),
            ("aarch64-unknown-darwin24.6", "aarch64-apple-macosx15.6", "Darwin"),
            ("aarch64-apple-darwin24.6", "aarch64-unknown-darwin24.6", "Darwin"),
            ("aarch64-apple-ios17.0", "aarch64-apple-macosx15.6", "Darwin"),
            ("aarch64-apple-darwin24.6-simulator", "aarch64-apple-macosx15.6", "Darwin"),
            ("aarch64-apple-darwin24.6", "aarch64-apple-macosx15.6", "Linux"),
            ("aarch64-unknown-linux-gnu", "x86_64-unknown-linux-gnu", "Linux"),
        ):
            with self.subTest(build=build, host=host, platform=platform):
                result = self.probe("roles", build, host, platform)
                self.assertNotEqual(result.returncode, 0)

        # Exact GNU/Linux build/host matches remain admitted as before.
        same = self.probe(
            "roles", "x86_64-unknown-linux-gnu",
            "x86_64-unknown-linux-gnu", "Linux",
        )
        self.assertEqual(same.returncode, 0, same.stderr)

    def test_darwin_process_matches_product_or_kernel_target(self):
        for triple, process, accepted in (
            ("aarch64-apple-darwin24.6", "arm64", True),
            ("aarch64-apple-macosx15.6", "arm64", True),
            ("arm64-apple-macosx15.6", "aarch64", True),
            ("x86_64-apple-darwin22", "x86_64", True),
            ("x86_64-apple-macosx13.0", "x86_64", True),
            ("aarch64-unknown-darwin24.6", "arm64", False),
            ("aarch64-apple-ios17.0", "arm64", False),
            ("arm64e-apple-macosx27.2", "arm64", False),
            ("x86_64-apple-macosx15.6", "arm64", False),
            ("aarch64-apple-macosx15.6", "x86_64", False),
            ("aarch64-apple-macosx15.6-simulator", "arm64", False),
        ):
            with self.subTest(triple=triple, process=process):
                result = self.probe("process", triple, process)
                self.assertEqual(result.returncode == 0, accepted, result.stderr)

    def test_gnu_config_sub_keeps_equivalent_macos_hosts_native(self):
        # The real validator must accept an Apple arm64 -> aarch64
        # canonicalization, but never treat a foreign Darwin vendor as native.
        with tempfile.TemporaryDirectory(prefix="whp-gnu-triplet-") as temp:
            root = Path(temp)
            (root / "config.sub").write_text(
                '#!/bin/sh\n'
                'case "$1" in\n'
                '  arm64-apple-macosx15.6)\n'
                '    printf "aarch64-apple-macosx15.6\\n" ;;\n'
                '  arm64-unknown-darwin24.6)\n'
                '    printf "aarch64-unknown-darwin24.6\\n" ;;\n'
                '  powerpc-elf) printf "powerpc-unknown-elf\\n" ;;\n'
                '  *) printf "%s\\n" "$1" ;;\n'
                'esac\n',
                encoding="utf-8",
            )
            (root / "config.sub").chmod(0o700)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            (fake_bin / "uname").write_text(
                '#!/bin/sh\n'
                'if [ "$1" = -s ]; then printf "Darwin\\n"; exit 0; fi\n'
                'exec /usr/bin/uname "$@"\n',
                encoding="utf-8",
            )
            (fake_bin / "uname").chmod(0o700)
            script = (
                "set -euo pipefail\n"
                + DARWIN_ABI_HELPERS + "\n"
                + source_function("toolchain_build_host_triplets_match") + "\n"
                + source_function("validate_source_triplets") + "\n"
                + 'TOOLCHAIN_TARGET=powerpc-elf\n'
                + 'TOOLCHAIN_BUILD_TRIPLET="$1"\n'
                + 'TOOLCHAIN_HOST_TRIPLET="$1"\n'
                + 'TOOLCHAIN_CONFIGURE_BUILD_TRIPLET="$1"\n'
                + 'TOOLCHAIN_CONFIGURE_HOST_TRIPLET="$1"\n'
                + 'validate_source_triplets "$2" regression\n'
            )
            for value, accepted in (
                ("arm64-apple-macosx15.6", True),
                ("arm64-unknown-darwin24.6", False),
            ):
                with self.subTest(triple=value):
                    env = dict(os.environ)
                    env["PATH"] = str(fake_bin) + os.pathsep + env.get(
                        "PATH", "/usr/bin:/bin",
                    )
                    result = subprocess.run(
                        ["/bin/bash", "-c", script, "--", value, str(root)],
                        env=env, capture_output=True, text=True,
                        timeout=10, check=False,
                    )
                    self.assertEqual(
                        result.returncode == 0, accepted,
                        (result.stdout, result.stderr),
                    )

    def test_host_compilers_do_not_inherit_cross_artifact_compilers(self):
        assignments = [
            line for line in SOURCE.splitlines()
            if line.startswith(("TOOLCHAIN_HOST_CC=", "TOOLCHAIN_HOST_CXX="))
        ]
        self.assertEqual(len(assignments), 2)
        selection = (
            "set -euo pipefail\n" + "\n".join(assignments)
            + '\nprintf "%s|%s\\n" "$TOOLCHAIN_HOST_CC" "$TOOLCHAIN_HOST_CXX"\n'
        )
        cases = (
            ({}, "cc|c++"),
            (
                {"CC_FOR_BUILD": "/build/native-cc",
                 "CXX_FOR_BUILD": "/build/native-cxx"},
                "/build/native-cc|/build/native-cxx",
            ),
            (
                {"CC_FOR_BUILD": "/build/native-cc",
                 "CXX_FOR_BUILD": "/build/native-cxx",
                 "TOOLCHAIN_HOST_CC": "/explicit/toolchain-cc",
                 "TOOLCHAIN_HOST_CXX": "/explicit/toolchain-cxx"},
                "/explicit/toolchain-cc|/explicit/toolchain-cxx",
            ),
        )
        for overrides, expected in cases:
            with self.subTest(overrides=overrides):
                env = os.environ.copy()
                for key in (
                    "CC", "CXX", "CC_FOR_BUILD", "CXX_FOR_BUILD",
                    "TOOLCHAIN_HOST_CC", "TOOLCHAIN_HOST_CXX",
                ):
                    env.pop(key, None)
                env.update({
                    "CC": "powerpc-elf-gcc",
                    "CXX": "powerpc-elf-g++",
                    **overrides,
                })
                result = subprocess.run(
                    ["/bin/bash", "-c", selection],
                    env=env, capture_output=True, text=True,
                    timeout=10, check=False,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), expected)

    def test_guard_preserves_configure_triplets_and_target(self):
        self.assertIn(
            'source "$SOURCE_DIR/scripts/whp-build/macos-target-abi.bash"',
            SOURCE,
        )
        self.assertIn(
            '"$TOOLCHAIN_BUILD_TRIPLET" "$TOOLCHAIN_HOST_TRIPLET" "$(uname -s)"',
            SOURCE,
        )
        self.assertIn(
            '"$TOOLCHAIN_BUILD_TRIPLET" "$(uname -m)"', SOURCE,
        )
        self.assertIn("BUILD_TRIPLET=$TOOLCHAIN_BUILD_TRIPLET", SOURCE)
        self.assertIn("HOST_TRIPLET=$TOOLCHAIN_HOST_TRIPLET", SOURCE)
        self.assertIn("GNU_CONFIGURE_BUILD_TRIPLET=$TOOLCHAIN_CONFIGURE_BUILD_TRIPLET", SOURCE)
        self.assertIn("GNU_CONFIGURE_HOST_TRIPLET=$TOOLCHAIN_CONFIGURE_HOST_TRIPLET", SOURCE)
        self.assertIn("TOOLCHAIN_CONFIGURE_HOST_TRIPLET=", SOURCE)
        self.assertIn(
            'TOOLCHAIN_CONFIGURE_HOST_TRIPLET="$TOOLCHAIN_CONFIGURE_BUILD_TRIPLET"',
            SOURCE,
        )
        self.assertEqual(
            SOURCE.count('--build="$TOOLCHAIN_CONFIGURE_BUILD_TRIPLET"'), 2,
        )
        self.assertEqual(
            SOURCE.count('--host="$TOOLCHAIN_CONFIGURE_HOST_TRIPLET"'), 2,
        )
        self.assertIn("BOOTSTRAP_SCHEMA=8", SOURCE)
        self.assertIn("TOOLCHAIN_TARGET=", SOURCE)
        self.assertIn("powerpc-elf", SOURCE)


if __name__ == "__main__":
    unittest.main()
