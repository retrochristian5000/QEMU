#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Host pkg-config seed contract; no network or package manager required."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SEED = ROOT / "seeds/pkg-config.sh"
PREPARE = ROOT / "scripts/whp-build/prepare-build.bash"


class PkgConfigSeedTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.bin = Path(self.temp.name)
        self.pkgconf = self.fake("pkgconf")
        self.pkgconfig = self.fake("pkg-config")

    def fake(self, name):
        path = self.bin / name
        path.write_text(
            '#!/bin/sh\n'
            'case "$1" in\n'
            '  --version) printf "2.2.0\\n" ;;\n'
            '  --libs) printf "%s\\n" "$0" ;;\n'
            '  *) exit 1 ;;\n'
            'esac\n',
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def run_seed(self, *args, **variables):
        env = {"PATH": str(self.bin), "HOME": self.temp.name}
        env.update(variables)
        return subprocess.run(
            ["/bin/sh", str(SEED), *args], env=env,
            text=True, capture_output=True, check=False,
        )

    def test_pkg_config_precedes_pkgconf(self):
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.pkgconfig))

    def test_pkgconf_fallback_when_pkg_config_absent(self):
        self.pkgconfig.unlink()
        result = self.run_seed("--print-seed")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.pkgconf))

    def test_explicit_build_machine_override(self):
        result = self.run_seed(
            "--print-seed", PKG_CONFIG_FOR_BUILD=str(self.pkgconf),
            PKG_CONFIG=str(self.pkgconfig),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.pkgconf))

    def test_seed_override_is_authoritative(self):
        result = self.run_seed(
            "--libs", WHP_PKG_CONFIG_SEED=str(self.pkgconf),
            PKG_CONFIG_FOR_BUILD=str(self.pkgconfig),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), str(self.pkgconf))

    def test_invalid_explicit_never_falls_back(self):
        result = self.run_seed(
            "--print-seed", PKG_CONFIG_FOR_BUILD=str(self.bin / "missing"),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("PKG_CONFIG_FOR_BUILD", result.stderr)

    def test_self_reference_is_rejected(self):
        result = self.run_seed(
            "--print-seed", WHP_PKG_CONFIG_SEED=str(SEED),
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("WHP_PKG_CONFIG_SEED", result.stderr)

    def test_provider_selection_precedes_host_seed(self):
        source = PREPARE.read_text(encoding="utf-8")
        self.assertIn('seeds/pkg-config.sh', source)
        self.assertLess(
            source.index('export WHP_MACOS_DEPENDENCY_PROVIDER'),
            source.index('seeds/pkg-config.sh'),
        )
        self.assertIn('export PKG_CONFIG_FOR_BUILD', source)
        self.assertNotIn('PKG_CONFIG="$(/bin/sh', source)


if __name__ == "__main__":
    unittest.main()
