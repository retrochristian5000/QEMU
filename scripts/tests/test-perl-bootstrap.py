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
    assert "reconcile_submodule(ROOT, REL, git=git)" in source
    assert 'stage_source(revision, source, git=git)' in source
    assert '"./Configure", "-des"' in source
    assert 'run([make, "perl"]' in source
    assert 'run([make, "install"]' in source
    assert 'valid_perl(executable)' in source
    assert 'f"SEED_PERL={seed}' in source
    assert 'env["PERL"] = seed' in source
    assert 'env["CC_FOR_BUILD"] = cc' in source
    assert 'env["SDKROOT"] = sdk' in source
    assert "-Uuseshrplib" in source
    assert 'marker_path.write_text(marker' in source

    host = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    assert host.index("whp_prepare_bootstrap_zlib") < host.index("BOOTSTRAP_PERL=$(")
    assert host.index("BOOTSTRAP_PERL=$(") < host.index("BOOTSTRAP_AUTOMAKE=$(")
    assert host.index("BOOTSTRAP_AUTOMAKE=$(") < host.index("BOOTSTRAP_AUTOCONF=$(")
    assert host.index("BOOTSTRAP_AUTOCONF=$(") < host.index("BOOTSTRAP_GAWK=$(")
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
        assert not perl.valid_perl(bad)

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
