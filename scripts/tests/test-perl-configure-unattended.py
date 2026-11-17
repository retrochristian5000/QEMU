#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Perl Configure's development-release and unattended execution contract."""

import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "whp_perl_configure", ROOT / "scripts" / "ensure-perl.py"
)
assert SPEC and SPEC.loader
perl = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(perl)


class PerlConfigureTests(unittest.TestCase):
    def configure(self, minor: int):
        with tempfile.TemporaryDirectory(prefix="whp-perl-configure-") as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text(
                f"#define PERL_REVISION 5\n#define PERL_VERSION\t{minor}\t/* epoch */\n"
                "#define PERL_SUBVERSION 5\n", encoding="utf-8"
            )
            return perl.configure_arguments(source, source / "prefix", "/usr/bin/cc")

    def test_odd_development_series_requires_explicit_consent(self):
        args = self.configure(45)
        self.assertIn("-des", args)
        self.assertIn("-Dusedevel", args)
        self.assertIn("-Uuseshrplib", args)
        self.assertIn("-Uversiononly", args)

    def test_even_stable_series_does_not_enable_development(self):
        args = self.configure(44)
        self.assertIn("-des", args)
        self.assertNotIn("-Dusedevel", args)
        self.assertIn("-Uversiononly", args)

    def test_unknown_source_version_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text("#define PERL_VERSION bad\n")
            with self.assertRaisesRegex(RuntimeError, "PERL_VERSION"):
                perl.configure_arguments(source, source / "prefix", "cc")

    def test_configure_cannot_read_interactive_stdin(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Configure").write_text(
                '#!/bin/sh\n'
                'if IFS= read -r answer; then\n'
                '  echo "interactive input accepted" >&2; exit 31\n'
                'fi\n'
                'printf "unattended\\n"\n',
                encoding="utf-8",
            )
            result = perl.run(
                ["/bin/sh", "./Configure", "-des"], cwd=source,
                unattended=True, capture=True, timeout=5,
            )
            self.assertEqual(result, "unattended\n")

    def test_subprocess_timeout_has_actionable_error(self):
        with mock.patch.object(
            perl.subprocess, "run",
            side_effect=subprocess.TimeoutExpired(["/bin/sh", "Configure"], 1),
        ):
            with self.assertRaisesRegex(RuntimeError, "exceeded 1s"):
                perl.run(["/bin/sh", "Configure"], unattended=True, timeout=1)

    def test_rebuild_rollback_restores_previous_prefix(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            prefix = base / "deps" / "perl"
            backup = base / "bootstrap" / "perl-previous-install"
            prefix.mkdir(parents=True)
            backup.parent.mkdir(parents=True)
            (prefix / "broken").write_text("partial", encoding="utf-8")
            (backup / "bin").mkdir(parents=True)
            (backup / "bin" / "perl").write_text("previous", encoding="utf-8")
            perl.restore_previous_install(prefix, backup)
            self.assertFalse(backup.exists())
            self.assertFalse((prefix / "broken").exists())
            self.assertEqual(
                (prefix / "bin" / "perl").read_text(encoding="utf-8"),
                "previous",
            )

    def test_lock_is_released_after_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            with self.assertRaisesRegex(RuntimeError, "probe"):
                with perl.bootstrap_lock(base):
                    raise RuntimeError("probe")
            with perl.bootstrap_lock(base):
                self.assertTrue((base / "bootstrap" / ".perl-bootstrap.lock").exists())

    def test_bad_make_seed_fails_before_perl(self):
        with tempfile.TemporaryDirectory() as tmp:
            fake = Path(tmp) / "make"
            fake.write_text(
                "#!/bin/sh\\nprintf 'Unrelated Make 1.0\\\\n'\\n",
                encoding="utf-8",
            )
            fake.chmod(0o755)
            with mock.patch.dict("os.environ", {"MAKE_CMD": str(fake)}):
                with self.assertRaisesRegex(RuntimeError, "GNU Make seed"):
                    perl.select_seed_make()

    def test_missing_explicit_make_is_not_replaced(self):
        with mock.patch.dict(
            "os.environ", {"MAKE_CMD": "/missing/whp-make"},
        ):
            with self.assertRaisesRegex(RuntimeError, "GNU Make"):
                perl.select_seed_make()

    def test_native_ar_and_ranlib_are_configured_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text(
                "#define PERL_VERSION 44\\n", encoding="utf-8"
            )
            args = perl.configure_arguments(
                source, source / "prefix", "/usr/bin/cc",
                "-O2", "", "/usr/bin/ranlib", "/usr/bin/ar",
            )
            self.assertIn("-Dranlib=/usr/bin/ranlib", args)
            self.assertIn("-Dar=/usr/bin/ar", args)
            self.assertIn("-Dfull_ar=/usr/bin/ar", args)
            self.assertIn("-Dld=/usr/bin/cc", args)

    def test_makefile_archive_tool_must_match_admitted_seed(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            makefile = source / "Makefile"
            makefile.write_text("AR = /usr/bin/ar\nranlib = /usr/bin/ranlib\n",
                                encoding="utf-8")
            perl.require_configured_ar(source, "/usr/bin/ar")
            with self.assertRaisesRegex(RuntimeError, "Makefile ar mismatch"):
                perl.require_configured_ar(source, "/unexpected/ar")
            makefile.write_text("AR = /usr/bin/ar\nAR = /usr/bin/ar\n",
                                encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "missing or ambiguous"):
                perl.require_configured_ar(source, "/usr/bin/ar")
            makefile.unlink()
            with self.assertRaisesRegex(RuntimeError, "did not generate a Makefile"):
                perl.require_configured_ar(source, "/usr/bin/ar")

    def test_phase_logs_keep_full_output_and_surface_errors(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            log = source / "compile.log"
            with mock.patch.dict("os.environ", {"WHP_PERL_VERBOSE": "1"}):
                with mock.patch("sys.stderr", new_callable=io.StringIO) as trace:
                    perl.run(
                        ["/bin/sh", "-c", "printf 'compiled\\n'"],
                        cwd=source, phase="compile", log_path=log,
                    )
                self.assertIn("compile start", trace.getvalue())
                self.assertIn("compile complete", trace.getvalue())
            self.assertEqual(log.read_text(), "compiled\n")

            with self.assertRaisesRegex(RuntimeError, "compile failed") as failure:
                perl.run(
                    ["/bin/sh", "-c",
                     "printf 'archive missing\\n' >&2; exit 23"],
                    cwd=source, phase="compile", log_path=log,
                )
            self.assertIn("exit 23", str(failure.exception))
            self.assertIn("archive missing", str(failure.exception))
            self.assertIn(str(log), str(failure.exception))

    def test_missing_stage_executable_has_context(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(RuntimeError, "install could not start") as failure:
                perl.run(
                    [str(Path(tmp) / "missing-executable")],
                    cwd=Path(tmp), phase="install",
                    log_path=Path(tmp) / "install.log",
                )
            self.assertIn(str(tmp), str(failure.exception))

    def test_native_ranlib_is_configured_explicitly(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text(
                "#define PERL_VERSION 44\\n", encoding="utf-8"
            )
            args = perl.configure_arguments(
                source, source / "prefix", "/usr/bin/cc",
                "-O2", "", "/usr/bin/ranlib",
            )
            self.assertIn("-Dranlib=/usr/bin/ranlib", args)

    def test_explicit_compiler_flags_reach_configure(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "patchlevel.h").write_text(
                "#define PERL_VERSION 44\\n", encoding="utf-8"
            )
            args = perl.configure_arguments(
                source, source / "prefix", "/usr/bin/cc",
                "-O2 -arch arm64", "-Wl,-dead_strip",
            )
            self.assertIn("-Dccflags=-O2 -arch arm64", args)
            self.assertIn("-Dldflags=-Wl,-dead_strip", args)

    def test_failed_configure_propagates_error(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp)
            (source / "Configure").write_text(
                '#!/bin/sh\nprintf "failed\\n" >&2\nexit 6\n',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "failed"):
                perl.run(["/bin/sh", "./Configure", "-des"], cwd=source,
                         unattended=True, capture=True, timeout=5)



class PerlEffectiveConfigureTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(prefix="whp-perl-result-")
        self.addCleanup(self.dir.cleanup)
        self.source = Path(self.dir.name)
        self.prefix = self.source / "managed Perl prefix"
        self.cc = "/usr/bin/cc"
        self.ar = "/usr/bin/ar"
        self.ranlib = "/usr/bin/ranlib"
        self.cflags = "-O2 -D_WHP_PERL=1"
        self.ldflags = "-Wl,-dead_strip"

    def configure_result(self, **overrides):
        values = {
            "prefix": str(self.prefix),
            "installbin": str(self.prefix / "bin"),
            "versiononly": "undef",
            "cc": self.cc,
            "ld": self.cc,
            "ar": self.ar,
            "full_ar": self.ar,
            "ranlib": self.ranlib,
            "ccflags": "-fno-common " + self.cflags,
            "ldflags": self.ldflags + " -pthread",
            "osname": "darwin",
        }
        values.update(overrides)
        # Config.sh is shell-assignment data.  Deliberately avoid sourcing it.
        (self.source / "config.sh").write_text(
            "".join(k + "='" + str(v) + "'\n" for k, v in values.items()),
            encoding="utf-8",
        )

    def verify(self):
        with mock.patch.object(perl.platform, "system", return_value="Darwin"):
            perl.require_configured_toolchain(
                self.source, self.prefix, self.cc, self.ar, self.ranlib,
                self.cflags, self.ldflags,
            )

    def test_effective_native_toolchain_accepts_hint_additions(self):
        self.configure_result()
        self.verify()

    def test_native_ar_index_fallback_is_explicitly_allowed(self):
        self.configure_result(ranlib=self.ar + " s")
        self.verify()

    def test_replaced_compiler_linker_and_prefix_fail(self):
        for key, bad in (
            ("cc", "/usr/bin/gcc"),
            ("ld", "/usr/bin/ld"),
            ("prefix", "/usr/local"),
            ("installbin", "/unexpected/another/bin"),
            ("ar", "/usr/bin/llvm-ar"),
            ("full_ar", "/usr/bin/llvm-ar"),
            ("ranlib", "/bin/true"),
            ("osname", "freebsd"),
        ):
            with self.subTest(key=key):
                self.configure_result(**{key: bad})
                with self.assertRaisesRegex(RuntimeError, "Perl Configure|unexpected archive"):
                    self.verify()

    def test_version_only_installation_cannot_pass_managed_validation(self):
        self.configure_result(versiononly="define")
        with self.assertRaisesRegex(RuntimeError, "version-only installation"):
            self.verify()

    def test_dropped_selected_compiler_or_linker_flag_fails(self):
        for key, value in (
            ("ccflags", "-fno-common -O2"),
            ("ldflags", "-pthread"),
        ):
            with self.subTest(key=key):
                self.configure_result(**{key: value})
                with self.assertRaisesRegex(RuntimeError, "dropped selected"):
                    self.verify()

    def test_malformed_and_duplicate_config_values_fail_closed(self):
        self.configure_result()
        with (self.source / "config.sh").open("a", encoding="utf-8") as output:
            output.write("cc='/unexpected'\n")
        with self.assertRaisesRegex(RuntimeError, "duplicate"):
            self.verify()
        self.configure_result(cc="'unterminated")
        with self.assertRaisesRegex(RuntimeError, "malformed"):
            self.verify()
        (self.source / "config.sh").unlink()
        with self.assertRaisesRegex(RuntimeError, "did not generate config.sh"):
            self.verify()

    def test_config_is_parsed_without_executing_shell(self):
        marker = self.source / "must-not-exist"
        self.configure_result(cc="$(touch " + str(marker) + ")")
        with self.assertRaisesRegex(RuntimeError, "replaced cc"):
            self.verify()
        self.assertFalse(marker.exists())


class PerlArchiveSelectionTests(unittest.TestCase):
    def test_ranlib_validates_the_exact_admitted_ar(self):
        chosen_ar = "/explicit/native/bin/ar"
        chosen_ranlib = "/explicit/native/bin/ranlib"
        calls = []

        def fake_run(argv, **kwargs):
            calls.append((argv, kwargs))
            if Path(argv[-2]).name == "ar.sh" and argv[-1] == "--print-seed":
                self.assertNotIn("env", kwargs)
                return subprocess.CompletedProcess(argv, 0, chosen_ar + "\n", "")
            if Path(argv[-2]).name == "ranlib.sh" and argv[-1] == "--print-seed":
                self.assertEqual(kwargs["env"]["WHP_AR_SEED"], chosen_ar)
                self.assertEqual(kwargs["env"]["AR_FOR_BUILD"], chosen_ar)
                return subprocess.CompletedProcess(argv, 0, chosen_ranlib + "\n", "")
            self.fail(f"unexpected command during archive selection: {argv!r}")

        with mock.patch.dict(perl.os.environ, {
            "AR_FOR_BUILD": chosen_ar,
            "AR": "/unrelated/target/bin/ar",
            "WHP_AR_SEED": "",
        }):
            with mock.patch.object(perl.subprocess, "run", side_effect=fake_run):
                self.assertEqual(
                    perl.select_native_archive_pair(),
                    (chosen_ar, chosen_ranlib),
                )
        self.assertEqual(len(calls), 2)

    def test_failed_ar_prevents_ranlib_rediscovery(self):
        attempts = []

        def fail_ar(argv, **kwargs):
            attempts.append(argv)
            return subprocess.CompletedProcess(argv, 7, "", "invalid native ar")

        with mock.patch.object(perl.subprocess, "run", side_effect=fail_ar):
            with self.assertRaisesRegex(RuntimeError, "native Perl ar seed unavailable"):
                perl.select_native_archive_pair()
        self.assertEqual(len(attempts), 1)
        self.assertEqual((Path(attempts[0][-2]).name, attempts[0][-1]), ("ar.sh", "--print-seed"))

    def test_failed_paired_ranlib_never_substitutes_another_ar(self):
        def fake_run(argv, **kwargs):
            if Path(argv[-2]).name == "ar.sh" and argv[-1] == "--print-seed":
                return subprocess.CompletedProcess(argv, 0, "/native/selected/ar\n", "")
            self.assertEqual(kwargs["env"]["WHP_AR_SEED"], "/native/selected/ar")
            return subprocess.CompletedProcess(argv, 5, "", "indexing failed")

        with mock.patch.object(perl.subprocess, "run", side_effect=fake_run):
            with self.assertRaisesRegex(RuntimeError, "native Perl ranlib seed unavailable"):
                perl.select_native_archive_pair()


if __name__ == "__main__":
    unittest.main()
