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

    def test_replaces_existing_binary_and_foreign_symlink_after_probe(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = self.backend(root)
            dest = root / alias.ALIAS
            dest.write_bytes(b"old 32-bit executable")
            self.assertEqual(alias.ensure_alias(root, check_only=True),
                             "replace-ready")
            self.assertEqual(dest.read_bytes(), b"old 32-bit executable")
            self.assertEqual(alias.ensure_alias(root), "replaced")
            self.assertTrue(dest.is_symlink())
            self.assertEqual(dest.resolve(), source.resolve())

            dest.unlink()
            other = root / "other-program"
            other.write_bytes(b"unrelated binary")
            dest.symlink_to(other.name)
            self.assertEqual(alias.ensure_alias(root, check_only=True),
                             "replace-ready")
            self.assertEqual(alias.ensure_alias(root), "replaced")
            self.assertEqual(os.readlink(dest), alias.BACKEND)
            self.assertEqual(other.read_bytes(), b"unrelated binary")
            self.assertFalse(any(root.glob(".whp-x86-family-*")))

    def test_directory_and_special_targets_are_never_replaced(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.backend(root)
            dest = root / alias.ALIAS
            dest.mkdir()
            with self.assertRaisesRegex(ValueError, "not a replaceable"):
                alias.ensure_alias(root)
            self.assertTrue(dest.is_dir())

    def test_backend_must_not_resolve_via_replacement_destination(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            destination = self.backend(root)
            old = root / alias.ALIAS
            destination.rename(old)
            destination.symlink_to(alias.ALIAS)
            with self.assertRaisesRegex(ValueError, "symbolic-link cycle"):
                alias.ensure_alias(root)
            self.assertTrue(destination.is_symlink())
            self.assertFalse(old.is_symlink())

    def test_failed_atomic_publication_preserves_old_artifact(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.backend(root)
            dest = root / alias.ALIAS
            dest.write_bytes(b"working old emulator")
            from unittest import mock
            with mock.patch.object(alias.os, "replace",
                                   side_effect=OSError("write denied")):
                with self.assertRaisesRegex(ValueError, "could not publish"):
                    alias.ensure_alias(root)
            self.assertEqual(dest.read_bytes(), b"working old emulator")
            self.assertFalse(any(root.glob(".whp-x86-family-*")))

    def test_rejects_backend_without_qemu32(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            program = root / alias.BACKEND
            program.write_text("#!/bin/sh\necho 'x86 qemu64'\n", encoding="utf-8")
            program.chmod(0o755)
            dest = root / alias.ALIAS
            dest.write_bytes(b"working old i386 emulator")
            with self.assertRaisesRegex(ValueError, "qemu32 CPU model"):
                alias.ensure_alias(root)
            self.assertEqual(dest.read_bytes(), b"working old i386 emulator")


if __name__ == "__main__":
    unittest.main()
