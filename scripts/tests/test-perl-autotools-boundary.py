#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate native Perl -> Automake -> Autoconf runtime isolation."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
POISON = {
    "PERL5LIB": "/unrelated/perl/lib",
    "PERLLIB": "/legacy/perl/lib",
    "PERL5OPT": "-MNoSuchWHPBootstrapModule",
    "PERL5DB": "/unrelated/db.pl",
    "PERL_LOCAL_LIB_ROOT": "/unrelated/local",
    "PERL_MM_OPT": "INSTALL_BASE=/unrelated",
    "PERL_MB_OPT": "--install_base /unrelated",
}


def load(filename):
    target = ROOT / "scripts" / filename
    spec = importlib.util.spec_from_file_location(filename.replace("-", "_"), target)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {target}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PERL = load("ensure-perl.py")
AUTOMAKE = load("ensure-automake.py")
AUTOCONF = load("ensure-autoconf.py")
ENV = load("bootstrap_env.py")


class PerlAutotoolsBoundaryTests(unittest.TestCase):
    def test_environment_cleanup_preserves_selected_interpreter(self):
        original = {
            **POISON, "PERL": "/selected/perl", "WHP_PERL_SEED": "/selected/perl",
            "WHP_PERL_BOOTSTRAP_SEED": "/original/perl", "PATH": "/native/bin",
        }
        result = ENV.clean_host_environment(original)
        for name in POISON:
            self.assertNotIn(name, result)
        for name in ("PERL", "WHP_PERL_SEED", "WHP_PERL_BOOTSTRAP_SEED", "PATH"):
            self.assertEqual(result[name], original[name])

    def test_autotools_perl_selection_ignores_local_module_injection(self):
        for helper in (AUTOMAKE, AUTOCONF):
            with self.subTest(helper=helper.__name__):
                def observed(args, **kwargs):
                    self.assertEqual(args[-1], "--print-seed")
                    self.assertEqual(kwargs["env"]["PERL"], "/selected/perl")
                    for name in POISON:
                        self.assertNotIn(name, kwargs["env"])
                    return subprocess.CompletedProcess(args, 0, "/selected/perl\n", "")
                with (
                    mock.patch.dict(os.environ, {**POISON, "PERL": "/selected/perl"}),
                    mock.patch.object(helper.subprocess, "run", side_effect=observed),
                ):
                    self.assertEqual(helper.select_seed_perl(), "/selected/perl")

    def test_managed_perl_checks_autoconf_modules_and_sanitizes_environment(self):
        native = shutil.which("perl")
        if not native:
            self.skipTest("no native Perl interpreter")
        with mock.patch.dict(os.environ, POISON):
            reasons = []
            self.assertTrue(PERL.valid_perl(Path(native), reasons), reasons)
        reasons = []
        def failed_module(argv, **kwargs):
            self.assertEqual(argv[1], "-e")
            for mod in ("File::Temp", "File::Spec", "Getopt::Long",
                        "Text::ParseWords", "IO::File", "POSIX"):
                self.assertIn(mod, argv[2])
            self.assertNotIn("Time::HiRes", argv[2])
            for name in POISON:
                self.assertNotIn(name, kwargs["env"])
            return subprocess.CompletedProcess(
                argv, 42, "", "WHP_PERL_MODULE:File::Temp:Can't locate File/Temp.pm"
            )
        with (
            mock.patch.dict(os.environ, POISON),
            mock.patch.object(PERL.subprocess, "run", side_effect=failed_module),
        ):
            self.assertFalse(PERL.valid_perl(Path(native), reasons))
        self.assertIn("core module 'File::Temp' failed to load", reasons[0])

    def test_root_bootstrap_keeps_independent_seed(self):
        def observed(argv, **kwargs):
            self.assertEqual(kwargs["env"]["PERL"], "/original/perl")
            self.assertEqual(kwargs["env"]["WHP_PERL_SEED"], "/original/perl")
            for name in POISON:
                self.assertNotIn(name, kwargs["env"])
            return subprocess.CompletedProcess(argv, 0, "/original/perl\n", "")
        with (
            mock.patch.dict(os.environ, {
                **POISON, "WHP_PERL_BOOTSTRAP_SEED": "/original/perl",
                "WHP_PERL_SEED": "/managed/perl", "PERL": "/managed/perl",
            }),
            mock.patch.object(PERL.subprocess, "run", side_effect=observed),
        ):
            self.assertEqual(PERL.root_perl(), "/original/perl")


if __name__ == "__main__":
    unittest.main()
