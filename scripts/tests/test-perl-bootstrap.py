#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Pinned Perl bootstrap provenance, native interpreter, and cycle contracts."""

import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts/ensure-perl.py"
spec = importlib.util.spec_from_file_location("whp_ensure_perl", SCRIPT)
assert spec and spec.loader
perl = importlib.util.module_from_spec(spec)
spec.loader.exec_module(perl)


def check():
    modules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    assert '[submodule "toolchains/perl"]' in modules
    assert "https://github.com/retrochristian5000/perl.git" in modules
    gitlink = subprocess.run(
        ["git", "-C", str(ROOT), "ls-tree", "HEAD", "--", "toolchains/perl"],
        capture_output=True, text=True, check=False,
    )
    assert gitlink.returncode == 0
    assert gitlink.stdout.startswith("160000 commit "), gitlink.stdout

    source = SCRIPT.read_text(encoding="utf-8")
    # The native archiver's named probe stages must use the SDK-aware cc.sh
    # execution bridge, including incremental replacement and link/run.
    archive_seed = (ROOT / "seeds/ar.sh").read_text(encoding="utf-8")
    assert 'compiler_seed="$root/seeds/cc.sh"' in archive_seed
    for stage in ("compile-first-member", "compile-replacement-member",
                  "link-native-executable"):
        assert f'whp_ar_probe_step {stage} /bin/sh "$compiler_seed"' in archive_seed
    assert 'whp_ar_probe_step create-archive "$archiver" rc' in archive_seed
    assert 'whp_ar_probe_step replace-and-index "$archiver" rcs' in archive_seed
    assert 'whp_ar_probe_step run-linked-executable "$tmp/probe"' in archive_seed
    assert '"$compiler" -c "$tmp/probe.c"' not in archive_seed

    # The ranlib admission test must create an unindexed archive with the
    # already selected ar, then index, link, and run using native cc.sh.
    ranlib_seed = (ROOT / "seeds/ranlib.sh").read_text(encoding="utf-8")
    assert 'cc_seed="$root/seeds/cc.sh"' in ranlib_seed
    assert 'whp_ranlib_probe_step compile-member /bin/sh "$cc_seed"' in ranlib_seed
    assert 'whp_ranlib_probe_step create-unindexed-archive "$ar" rcS' in ranlib_seed
    assert 'whp_ranlib_probe_step index-archive "$ranlib"' in ranlib_seed
    assert 'whp_ranlib_probe_step link-native-executable /bin/sh "$cc_seed"' in ranlib_seed
    assert 'whp_ranlib_probe_step run-linked-executable "$dir/probe"' in ranlib_seed
    assert 'ranlib_env["WHP_AR_SEED"] = ar_path' in source
    assert 'env=ranlib_env' in source

    assert "reconcile_submodule(ROOT, REL, git=git)" in source
    # Missing native archive dependencies must fail before source checkout.
    assert source.index('str(ROOT / "seeds" / "ar.sh")') < source.index(
        "reconcile_submodule(ROOT, REL, git=git)"
    )
    assert source.index('str(ROOT / "seeds" / "ranlib.sh")') < source.index(
        "reconcile_submodule(ROOT, REL, git=git)"
    )
    assert source.index("select_native_sdk(ROOT)") < source.index(
        "reconcile_submodule(ROOT, REL, git=git)"
    )
    assert 'stage_source(revision, source, git=git)' in source
    assert '"./Configure", "-des"' in source
    assert 'run([make, "perl"]' in source
    assert 'run([make, "install"]' in source
    assert 'valid_perl(executable)' in source
    assert 'valid_perl(executable, validation_failures)' in source
    assert "managed Perl failed installed interpreter/module/OS checks" not in source
    assert 'f"SEED_PERL={seed}' in source
    assert 'env["PERL"] = seed' in source
    assert 'env=clean_host_environment(os.environ)' in source
    assert 'Text::ParseWords Time::HiRes' in source
    assert 'env["CC_FOR_BUILD"] = cc' in source
    assert 'env["SDKROOT"] = sdk' in source
    assert "-Uuseshrplib" in source
    assert 'temporary_marker.replace(marker_path)' in source
    assert 'make = select_seed_make()' in source
    assert source.index('make = select_seed_make()') < source.index(
        "reconcile_submodule(ROOT, REL, git=git)"
    )

    host = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    assert host.index("whp_prepare_bootstrap_zlib") < host.index("BOOTSTRAP_PERL=$(")
    assert host.index("BOOTSTRAP_PERL=$(") < host.index("BOOTSTRAP_AUTOMAKE=$(")
    assert host.index("BOOTSTRAP_AUTOMAKE=$(") < host.index("BOOTSTRAP_AUTOCONF=$(")
    # Gawk's promotion is independent; it need not follow Autoconf.
    # The required cycle boundary is Perl -> Automake -> Autoconf.
    assert host.index("WHP_PERL_SEED=$WHP_MANAGED_PERL") < host.index("BOOTSTRAP_AUTOMAKE=$(")
    assert 'WHP_PERL_BOOTSTRAP_SEED=$WHP_PERL_ROOT' in host
    assert 'WHP_PERL_SEED=$WHP_MANAGED_PERL' in host
    assert "BOOTSTRAP_PERL=1 requested" in host

    config = (ROOT / "scripts/whp-config/config.py").read_text()
    schema = (ROOT / "scripts/whp-config/menu-options.def").read_text()
    assert "Option('BOOTSTRAP_PERL', 'Host features'" in config
    assert "'BOOTSTRAP_PERL'," in config
    assert "BOOTSTRAP_PERL|Host features|" in schema

    # Semantic tests distinguish a functioning Perl from a plausible filename.
    with tempfile.TemporaryDirectory(prefix="whp-perl-policy-") as temp:
        bad = Path(temp) / "perl"
        bad.write_text(
            "#!/bin/sh\nprintf '%s\\n' 'This is perl 99.99'\n",
            encoding="utf-8",
        )
        bad.chmod(0o755)
        reasons = []
        assert not perl.valid_perl(bad, reasons)
        assert "unexpected validation output" in reasons[0]
        assert "This is perl 99.99" in reasons[0]

        missing = Path(temp) / "missing-perl"
        reasons = []
        assert not perl.valid_perl(missing, reasons)
        assert "executable is missing" in reasons[0]

        bad.chmod(0o644)
        reasons = []
        assert not perl.valid_perl(bad, reasons)
        assert "not executable" in reasons[0]
        bad.chmod(0o755)

        cases = (
            (42, "", "WHP_PERL_MODULE:Config:Can't locate Config.pm",
             "core module 'Config' failed to load"),
            (41, "", "WHP_PERL_VERSION:Perl 5.006 required",
             "interpreter version check failed"),
            (139, "", "segmentation fault", "exited with status 139"),
            (0, "whp-perl-native:", "", "empty osname"),
            (0, "unrecognized output", "", "unexpected validation output"),
        )
        for code, stdout, stderr, expected in cases:
            result = subprocess.CompletedProcess(
                [str(bad)], code, stdout, stderr,
            )
            with mock.patch.object(perl.subprocess, "run",
                                   return_value=result):
                reasons = []
                assert not perl.valid_perl(bad, reasons)
                assert expected in reasons[0], reasons

        with mock.patch.object(perl.subprocess, "run",
                               return_value=subprocess.CompletedProcess(
                                   [str(bad)], 0, "whp-perl-native:linux\n", ""
                               )), mock.patch.object(
                                   perl.platform, "system",
                                   return_value="Darwin"):
            reasons = []
            assert not perl.valid_perl(bad, reasons)
            assert "reported='linux', expected='darwin'" in reasons[0]

        with mock.patch.object(perl.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(
                                   [str(bad)], 15)):
            reasons = []
            assert not perl.valid_perl(bad, reasons)
            assert "timed out after 15 seconds" in reasons[0]

    original = shutil.which("perl")
    if original:
        assert perl.valid_perl(Path(original))
        with mock.patch.dict(os.environ, {
            "WHP_PERL_BOOTSTRAP_SEED": original,
            "WHP_PERL_SEED": "/not-yet-built/deps/perl/bin/perl",
            "PERL": "/not-yet-built/deps/perl/bin/perl",
        }):
            assert perl.root_perl() == original
    print("Pinned Perl source, independent seed, and native promotion: verified")


if __name__ == "__main__":
    check()
