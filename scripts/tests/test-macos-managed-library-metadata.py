#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate restoration of QEMU-managed library metadata after macOS hygiene."""

import os
from pathlib import Path
import subprocess
import tempfile
import unittest

HYGIENE = Path(__file__).resolve().parents[1] / "macos-build-hygiene.bash"


class ManagedMetadataTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.build = Path(self.temp.name) / "build"
        self.build.mkdir()
        self.env = dict(os.environ, BUILD_DIR=str(self.build), WHP_HYGIENE=str(HYGIENE))

    def run_bash(self, command, **kwargs):
        return subprocess.run(
            ["bash", "-c", 'source "$WHP_HYGIENE"\n' + command],
            env=dict(self.env, **kwargs), text=True, capture_output=True,
            check=False,
        )

    def make_pkg(self, name, module, marker, libdir):
        prefix = self.build / "deps" / name
        pcdir = prefix / libdir / "pkgconfig"
        pcdir.mkdir(parents=True)
        (prefix / marker).touch()
        (pcdir / (module + ".pc")).touch()
        return prefix, pcdir

    def test_restores_all_four_libraries_including_lib64_and_libdata(self):
        cases = [
            ("zlib-artifact", "zlib", ".whp-zlib-bootstrap", "libdata"),
            ("jack", "jack", ".whp-jack-bootstrap", "lib64"),
            ("sdl3", "sdl3", ".whp-sdl-bootstrap", "lib"),
            ("libisofs", "libisofs-1", ".whp-libisofs-bootstrap", "lib"),
        ]
        cmds = ["unset PKG_CONFIG_PATH CMAKE_PREFIX_PATH"]
        pcdirs = []
        for name, module, marker, libdir in cases:
            prefix, pcdir = self.make_pkg(name, module, marker, libdir)
            pcdirs.append(str(pcdir))
            cmds.append(
                f'whp_restore_managed_pkg_config {name} {module} {marker} "{prefix}"'
            )
        cmds.append('printf "%s\n" "$PKG_CONFIG_PATH"')
        result = self.run_bash("\n".join(cmds))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip().split(":"), list(reversed(pcdirs)))
        self.assertIn("managed library metadata: JACK", result.stderr)

    def test_rejects_external_and_incomplete_prefix(self):
        foreign = Path(self.temp.name) / "other"
        foreign.mkdir()
        bad = self.run_bash(
            'whp_restore_managed_pkg_config JACK jack .whp-jack-bootstrap "$FOREIGN"',
            FOREIGN=str(foreign),
        )
        self.assertNotEqual(bad.returncode, 0)
        self.assertIn("outside the QEMU build dependencies", bad.stderr)
        prefix = self.build / "deps" / "jack"
        prefix.mkdir(parents=True)
        missing = self.run_bash(
            'whp_restore_managed_pkg_config JACK jack .whp-jack-bootstrap "$PREFIX"',
            PREFIX=str(prefix),
        )
        self.assertIn("bootstrap marker is missing", missing.stderr)
        (prefix / ".whp-jack-bootstrap").touch()
        missing_pc = self.run_bash(
            'whp_restore_managed_pkg_config JACK jack .whp-jack-bootstrap "$PREFIX"',
            PREFIX=str(prefix),
        )
        self.assertIn("no jack.pc", missing_pc.stderr)

    def test_empty_optional_prefix_is_noop(self):
        result = self.run_bash(
            'whp_restore_managed_pkg_config JACK jack .whp-jack-bootstrap ""'
        )
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()
