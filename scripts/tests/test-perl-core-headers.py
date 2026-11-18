#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Isolated native compile regression for managed Perl's installed CORE headers."""

import importlib.util
import os
from pathlib import Path
import shlex
import shutil
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_perl_core_headers", ROOT / "scripts" / "ensure-perl.py"
)
assert SPEC and SPEC.loader
perl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(perl)


@unittest.skipUnless(shutil.which("cc"), "native C compiler required")
class ManagedPerlCoreHeadersTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="whp-perl-header-fixture-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.prefix = self.root / "managed prefix"
        self.archlib = self.prefix / "lib" / "perl5" / "arch"
        self.core = self.archlib / "CORE"
        self.core.mkdir(parents=True)
        self.work = self.root / "build work"
        self.compiler = shutil.which("cc")
        (self.core / "EXTERN.h").write_text(
            "#define WHP_PERL_EXTERNAL 1\n", encoding="utf-8"
        )
        (self.core / "config.h").write_text(
            "#define WHP_PERL_HEADER_CONFIG 1\n", encoding="utf-8"
        )
        (self.core / "embed.h").write_text(
            "#define WHP_PERL_EMBEDDED 1\n", encoding="utf-8"
        )
        (self.core / "perl.h").write_text(
            '#include "config.h"\n#include "embed.h"\n'
            "#if !defined(WHP_PERL_HEADER_CONFIG) || !defined(WHP_PERL_EMBEDDED)\n"
            '#error "Perl header configuration missing"\n#endif\n'
            "#ifndef WHP_PERL_CCFLAGS_OK\n"
            '#error "Perl Configure ccflags not applied"\n#endif\n'
            "#define PERL_REVISION 5\n", encoding="utf-8"
        )
        (self.core / "XSUB.h").write_text(
            "#define WHP_PERL_XS_HEADER 1\n", encoding="utf-8"
        )
        self.fake_perl = self.root / "fake installed perl"
        self.set_config()

    def set_config(self, ccflags="-DWHP_PERL_CCFLAGS_OK=1", cppflags="",
                   archlib=None):
        archlib = self.archlib if archlib is None else archlib
        # A minimal interpreter fixture emits Config's NUL-delimited fields.
        # Arguments are intentionally ignored; validation is in the real
        # source's Perl invocation and compile, not shell interpretation.
        self.fake_perl.write_text(
            "#!/bin/sh\n"
            "printf '%s\\000%s\\000%s' "
            f"{shlex.quote(str(archlib))} {shlex.quote(ccflags)} "
            f"{shlex.quote(cppflags)}\n",
            encoding="utf-8",
        )
        self.fake_perl.chmod(0o755)

    def verify(self):
        perl.validate_installed_core_headers(
            self.fake_perl, self.prefix, self.compiler, "", self.work
        )

    def test_valid_headers_compile_from_prefix_with_spaces(self):
        self.verify()
        self.assertTrue((self.work / "header-compile.log").is_file())

    def test_missing_xs_header_is_rejected_before_promotion(self):
        (self.core / "XSUB.h").unlink()
        with self.assertRaisesRegex(RuntimeError, "CORE header missing"):
            self.verify()

    def test_transitive_header_break_is_detected(self):
        (self.core / "embed.h").write_text(
            '#error "corrupt embedded header"\n', encoding="utf-8"
        )
        with self.assertRaisesRegex(RuntimeError, "CORE header compile failed"):
            self.verify()

    def test_wrong_prefix_cannot_borrow_seed_headers(self):
        other = self.root / "unrelated-perl" / "lib"
        other.mkdir(parents=True)
        self.set_config(archlib=other)
        with self.assertRaisesRegex(RuntimeError, "outside managed prefix"):
            self.verify()

    def test_malformed_perl_config_flags_fail_closed(self):
        self.set_config(ccflags='-I"unterminated')
        with self.assertRaisesRegex(RuntimeError, "Config C flags are malformed"):
            self.verify()

    def test_symlinked_header_outside_prefix_is_rejected(self):
        (self.core / "embed.h").unlink()
        external = self.root / "external-perl-header.h"
        external.write_text("#define WHP_PERL_EMBEDDED 1\\n", encoding="utf-8")
        (self.core / "embed.h").symlink_to(external)
        with self.assertRaisesRegex(RuntimeError, "header escapes managed prefix"):
            self.verify()


class PerlPromotionPolicyTests(unittest.TestCase):
    def test_validation_precedes_marker_and_runs_on_cache_hit(self):
        text = (ROOT / "scripts" / "ensure-perl.py").read_text(encoding="utf-8")
        self.assertIn("validate_installed_core_headers(executable, prefix, cc, sdk, work)", text)
        self.assertLess(
            text.rindex("validate_installed_core_headers(executable, prefix, cc, sdk, work)"),
            text.index("temporary_marker.replace(marker_path)"),
        )
        self.assertIn("SCHEMA = \"8\"SCHEMA = \"7\"", text)


if __name__ == "__main__":
    unittest.main()
