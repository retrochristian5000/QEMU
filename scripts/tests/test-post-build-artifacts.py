#!/usr/bin/env python3
"""Regression tests for the WHP post-build verifier's file handling."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
POST_BUILD = ROOT / "scripts" / "whp-build" / "post-build.bash"


class PostBuildArtifactTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="whp post-build ")
        self.addCleanup(temporary.cleanup)
        self.source = pathlib.Path(temporary.name)
        self.build = self.source / "build with spaces"
        self.build.mkdir()
        emulator = self.build / "qemu-system-ppc"
        emulator.write_text(
            "#!/bin/sh\n"
            "case \"$1\" in\n"
            "    -machine) printf 'powermac3_1   Test PowerMac\\nmac99   Test Mac\\n' ;;\n"
            "    --version) printf 'QEMU emulator version test\\n' ;;\n"
            "    *) exit 2 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        emulator.chmod(0o755)

    def verify(self, env_overrides=None):
        env = {
            **os.environ,
            "SOURCE_DIR": str(self.source),
            "BUILD_DIR": str(self.build),
            "QEMU_TARGET_LIST": "ppc-softmmu",
        }
        if env_overrides:
            env.update(env_overrides)
        return subprocess.run(
            [
                "bash", "--noprofile", "--norc", "-c",
                'source "$1"; whp_verify_build_outputs qemu-system-ppc',
                "post-build-test", str(POST_BUILD),
            ],
            env=env, capture_output=True, text=True, check=False,
        )

    def test_emulator_in_path_containing_spaces(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stderr)
        manifest = (self.build / ".whp-build-artifacts").read_text(
            encoding="utf-8"
        )
        self.assertIn(f"QEMU_SYSTEM_PPC={self.build}/qemu-system-ppc", manifest)
        self.assertIn("QEMU_SYSTEM_PPC_VERSION=QEMU emulator version test", manifest)
        self.assertIn("POWERMAC3_1_REGISTERED=yes", manifest)

    def test_failed_manifest_publication_removes_staging_file(self):
        fake_bin = self.source / "fake-bin"
        fake_bin.mkdir()
        fake_mv = fake_bin / "mv"
        fake_mv.write_text("#!/bin/sh\nexit 7\n", encoding="utf-8")
        fake_mv.chmod(0o755)
        result = self.verify({
            "PATH": str(fake_bin) + os.pathsep + os.environ.get("PATH", ""),
        })
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("failed to publish build artifact manifest", result.stderr)
        self.assertFalse(list(self.build.glob(".whp-build-artifacts.new.*")))
        self.assertFalse((self.build / ".whp-build-artifacts").exists())


if __name__ == "__main__":
    unittest.main()
