#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Non-destructive regression tests for the x86 system-family link utility."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

TOOL = Path(__file__).resolve().parents[1] / "whp-build" / "x86-family-alias.py"
spec = importlib.util.spec_from_file_location("whp_x86_family_alias", TOOL)
assert spec is not None and spec.loader is not None
alias = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alias)


@unittest.skipIf(os.name == "nt", "POSIX symlinks required")
class X86FamilyAliasTests(unittest.TestCase):
    def backend(self, root: Path) -> Path:
        program = root / alias.BACKEND
        program.write_text(
            "#!/bin/sh\n"
            "if [ \"$1\" = -cpu ] && [ \"$2\" = help ]; then\n"
            "  printf 'x86 qemu32\\nx86 qemu64\\n'\n"
            "  exit 0\n"
            "fi\n"
            "exit 2\n",
            encoding="utf-8",
        )
        program.chmod(0o755)
        return program

    def test_preflight_creates_nothing_and_then_is_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.backend(root)
            dest = root / alias.ALIAS
            self.assertEqual(alias.ensure_alias(root, check_only=True), "ready")
            self.assertFalse(os.path.lexists(dest))
            self.assertEqual(alias.ensure_alias(root), "created")
            self.assertTrue(dest.is_symlink())
            self.assertEqual(os.readlink(dest), alias.BACKEND)
            self.assertEqual(dest.resolve(), source.resolve())
            self.assertEqual(alias.ensure_alias(root), "already-present")

    def test_never_replaces_an_existing_binary_or_foreign_link(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.backend(root)
            dest = root / alias.ALIAS
            dest.write_bytes(b"protected 32-bit artifact")
            with self.assertRaisesRegex(ValueError, "refusing to replace"):
                alias.ensure_alias(root)
            self.assertEqual(dest.read_bytes(), b"protected 32-bit artifact")
            dest.unlink()
            dest.symlink_to("unrelated-executable")
            with self.assertRaisesRegex(ValueError, "foreign symbolic link"):
                alias.ensure_alias(root)
            self.assertEqual(os.readlink(dest), "unrelated-executable")

    def test_rejects_backend_without_qemu32(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / alias.BACKEND
            program.write_text("#!/bin/sh\necho 'x86 qemu64'\n", encoding="utf-8")
            program.chmod(0o755)
            with self.assertRaisesRegex(ValueError, "qemu32 CPU model"):
                alias.ensure_alias(root)
            self.assertFalse(os.path.lexists(root / alias.ALIAS))


if __name__ == "__main__":
    unittest.main()
