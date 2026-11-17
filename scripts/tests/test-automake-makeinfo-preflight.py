#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check Git-source Automake's GNU Texinfo preflight and tool-role boundary."""

import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_automake_makeinfo_test", ROOT / "scripts/ensure-automake.py"
)
assert SPEC and SPEC.loader
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)


class AutomakeMakeinfoTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="whp-automake-texinfo-")
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.other = self.root / "other makeinfo"
        self.good = self.create_tool(
            self.root / "tools with spaces" / "makeinfo",
            "texi2any (GNU texinfo) 7.2",
        )

    def create_tool(self, path, banner, *, converts=True):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            f"  --version) printf '%s\\n' '{banner}' ;;\n"
            "  --no-split)\n"
            '    [ "$2" = -o ] || exit 9\n'
            + ('    printf "GNU Texinfo test output\\n" > "$3"\n'
               if converts else '    exit 14\n')
            + "    ;;\n"
            "  *) exit 9 ;;\n"
            "esac\n",
            encoding="utf-8",
        )
        path.chmod(0o755)
        return path

    def test_explicit_tool_with_spaces_preserves_absolute_path(self):
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": str(self.good),
            "MAKEINFO": "/missing/unrelated-makeinfo",
        }):
            self.assertEqual(module.select_makeinfo(), str(self.good))

    def test_environment_makeinfo_reused_without_rediscovery(self):
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": "",
            "MAKEINFO": str(self.good),
        }):
            self.assertEqual(module.select_makeinfo(), str(self.good))

    def test_wrong_provider_is_rejected_even_with_valid_exit(self):
        wrong = self.create_tool(self.root / "fake", "Fake Docs 7.2")
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": str(wrong),
        }):
            with self.assertRaisesRegex(RuntimeError, "GNU Texinfo"):
                module.select_makeinfo()

    def test_version_only_script_is_not_an_admitted_generator(self):
        bad = self.create_tool(
            self.root / "version-only", "makeinfo (GNU texinfo) 7.2",
            converts=False,
        )
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": str(bad),
        }):
            with self.assertRaisesRegex(RuntimeError, "cannot convert"):
                module.select_makeinfo()

    def test_invalid_explicit_implementation_does_not_fallback(self):
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": str(self.root / "missing"),
            "MAKEINFO": str(self.good),
        }):
            with self.assertRaisesRegex(RuntimeError, "not executable"):
                module.select_makeinfo()
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": "makeinfo --force",
            "MAKEINFO": str(self.good),
        }):
            with self.assertRaisesRegex(RuntimeError, "one executable"):
                module.select_makeinfo()

    def test_missing_texinfo_reports_required_git_source_dependency(self):
        with mock.patch.dict(os.environ, {
            "WHP_AUTOMAKE_MAKEINFO_SEED": "", "MAKEINFO": "",
        }):
            with mock.patch.object(module, "executable", return_value=None):
                with self.assertRaisesRegex(RuntimeError, "required for a Git-source"):
                    module.select_makeinfo()

    def test_failed_preflight_never_starts_source_reconciliation(self):
        with (
            mock.patch.object(module, "select_seed_sed", return_value="/sed"),
            mock.patch.object(module, "select_seed_perl", return_value="/perl"),
            mock.patch.object(
                module, "select_seed_autoconf_pair",
                return_value=("/autoconf", "/autom4te"),
            ),
            mock.patch.object(module, "select_gnu_make", return_value="/make"),
            mock.patch.object(
                module, "select_makeinfo",
                side_effect=RuntimeError("missing GNU Texinfo"),
            ),
            mock.patch.object(module, "ensure_source") as reconcile,
        ):
            with self.assertRaisesRegex(RuntimeError, "missing GNU Texinfo"):
                module.bootstrap(self.root / "build")
            reconcile.assert_not_called()

    def test_marker_and_child_environment_are_bound_to_makeinfo(self):
        source = (ROOT / "scripts/ensure-automake.py").read_text(
            encoding="utf-8"
        )
        self.assertIn('env["MAKEINFO"] = makeinfo', source)
        self.assertIn('f"MAKEINFO={makeinfo}:', source)
        self.assertLess(
            source.index("makeinfo = select_makeinfo()"),
            source.index("revision = ensure_source()"),
        )


if __name__ == "__main__":
    unittest.main()
