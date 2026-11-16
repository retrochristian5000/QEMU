#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Focused, isolated regression for the QEMU post-bootstrap header auditor."""

from pathlib import Path
import os
import shutil
import subprocess
import sys
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1] / "whp-build" / "header-audit.py"


@unittest.skipUnless(shutil.which("cc") and shutil.which("ar"),
                     "native C compiler and ar required for integration fixture")
class HeaderAuditTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="whp headers ")
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        include = root / "include path"
        include.mkdir()
        (include / "whp_test.h").write_text(
            "#ifndef WHP_TEST_H\n#define WHP_TEST_H\n"
            "int whp_test_value(void);\n#endif\n", encoding="utf-8")
        source = root / "library.c"
        source.write_text("int whp_test_value(void) { return 4; }\n", encoding="utf-8")
        obj = root / "library.o"
        self.lib = root / "libwhptest.a"
        subprocess.run(["cc", "-c", str(source), "-o", str(obj)], check=True)
        subprocess.run(["ar", "rcs", str(self.lib), str(obj)], check=True)
        self.pkg = root / "fake pkg-config"
        self.pkg.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            "  --atleast-version=*) shift ;;\n"
            "esac\n"
            'case "$1" in\n'
            '  --exists) [ "$2" = whp-test ] ;;\n'
            "  --modversion) printf '1.0\\n' ;;\n"
            f"  --cflags) printf '%s\\n' '-I\"{include}\"' ;;\n"
            f"  --libs) printf '%s\\n' '-L\"{root}\" -lwhptest' ;;\n"
            "  *) exit 2 ;;\n"
            "esac\n", encoding="utf-8")
        self.pkg.chmod(0o755)
        self.env = os.environ.copy()
        self.env.pop("CPPFLAGS", None)
        self.env.pop("CFLAGS", None)
        self.env.pop("LDFLAGS", None)

    def invoke(self, *more):
        return subprocess.run([sys.executable, str(SCRIPT),
                               "--package", "whp-test", "--header", "whp_test.h",
                               "--function", "whp_test_value", "--cc", "cc",
                               "--pkg-config", str(self.pkg), *more],
                              capture_output=True, text=True, env=self.env)

    def test_complete_header_and_link(self):
        result = self.invoke()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PASS header dependency", result.stdout)
        self.assertIn("symbol=checked", result.stdout)

    def test_missing_header_reports_compile_failure(self):
        result = self.invoke("--header", "whp_missing.h")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("header compile", result.stderr)

    def test_missing_library_reports_link_failure(self):
        self.lib.unlink()
        result = self.invoke()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("dependency link", result.stderr)

    def test_package_metadata_failure(self):
        result = self.invoke("--package", "nonexistent")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("pkg-config discovery/version", result.stderr)

    def test_invalid_header_rejected(self):
        result = self.invoke("--header", "../../private.h")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("safe relative include path", result.stderr)


if __name__ == "__main__":
    unittest.main()
