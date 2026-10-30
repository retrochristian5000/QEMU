#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import os
import pathlib
import shutil
import tempfile
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / "scripts" / "ensure-sed.py"

spec = importlib.util.spec_from_file_location("whp_ensure_sed", HELPER)
if spec is None or spec.loader is None:
    raise SystemExit("error: could not load ensure-sed.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

source = HELPER.read_text(encoding="utf-8")
wrong = 'SUBMODULE_DIR / "build-aux" / "git-version-gen"'
right = 'SUBMODULE_DIR / NESTED_REL / "build-aux" / "git-version-gen"'
if wrong in source:
    raise SystemExit("error: sed bootstrap still expects generated git-version-gen in sed")
if right not in source:
    raise SystemExit("error: sed bootstrap does not source git-version-gen from gnulib")

with tempfile.TemporaryDirectory(prefix="whp-sed-version-") as td:
    sed_root = pathlib.Path(td)
    (sed_root / "gnulib" / "build-aux").mkdir(parents=True)
    (sed_root / "gnulib" / "build-aux" / "git-version-gen").write_text(
        "#!/bin/sh\n", encoding="utf-8"
    )
    (sed_root / "NEWS").write_text(
        """GNU sed NEWS

* Noteworthy changes in release ?.? (????-??-??) [?]

* Noteworthy changes in release 4.10 (2026-04-21) [stable]

* Noteworthy changes in release 4.9 (2022-11-06) [stable]
""",
        encoding="utf-8",
    )

    mod.SUBMODULE_DIR = sed_root

    fallback = mod.fallback_staged_version(
        "a179e7a8addabe81470b2da9d5d276e14ceeae13"
    )
    if fallback != "4.10.git-a179e7a8adda":
        raise SystemExit(f"error: unexpected sed fallback version: {fallback}")

    original_run_text = mod.run_text
    try:
        mod.run_text = lambda *args, **kwargs: "UNKNOWN"
        generated = mod.live_checkout_version(
            "a179e7a8addabe81470b2da9d5d276e14ceeae13"
        )
        if generated != fallback:
            raise SystemExit(
                "error: UNKNOWN git-version-gen output did not use deterministic fallback"
            )

        mod.run_text = lambda *args, **kwargs: "4.10.7-deadbeef"
        generated = mod.live_checkout_version(
            "a179e7a8addabe81470b2da9d5d276e14ceeae13"
        )
        if generated != "4.10.7-deadbeef":
            raise SystemExit(
                "error: valid git-version-gen output was unexpectedly rewritten"
            )
    finally:
        mod.run_text = original_run_text



# The selected CC must work with the *final* sanitized Autoconf environment,
# rather than only pass the earlier adapter's no-flags native seed test.
with tempfile.TemporaryDirectory(prefix="whp-sed-cc-contract-") as td:
    work = pathlib.Path(td)
    cc = shutil.which("cc") or shutil.which("clang")
    if not cc:
        raise SystemExit("error: no native C compiler for GNU sed smoke regression")
    env = os.environ.copy()
    for key in ("CFLAGS", "CPPFLAGS", "LDFLAGS"):
        env.pop(key, None)
    mod.validate_configure_compiler(cc, env, work)

    invalid = dict(env, CFLAGS="-fwhp-sed-deliberately-invalid-option")
    try:
        mod.validate_configure_compiler(cc, invalid, work)
    except RuntimeError as exc:
        if "GNU sed configure compiler cannot compile/link/run" not in str(exc):
            raise
        if "CFLAGS=-fwhp-sed-deliberately-invalid-option" not in str(exc):
            raise SystemExit("error: sed failed CC probe without flag diagnostics")
    else:
        raise SystemExit("error: GNU sed accepted unusable configure compiler flags")

    if list(work.glob("whp-sed-cc-*")):
        raise SystemExit("error: GNU sed compiler probe leaked a staging directory")

# Explicit -arch must be checked against its matching SDK and deployment.
# Auto mode still pins the SDK identity to prevent stale bootstrap reuse.
with patch.object(mod.platform, "system", return_value="Darwin"), \
     patch.object(mod, "select_macos_sdkroot", return_value="/mock/MacOSX.sdk"):
    with patch.dict(os.environ, {
        "WHP_MACOS_ARCH": "auto",
        "MACOSX_DEPLOYMENT_TARGET": "",
    }):
        apple_env = {}
        sdk, arch, deployment = mod.macos_environment(apple_env)
        if sdk != "/mock/MacOSX.sdk" or arch or deployment:
            raise SystemExit("error: sed auto SDK cache identity was lost")
        if apple_env.get("SDKROOT") != sdk or "CFLAGS" in apple_env:
            raise SystemExit("error: sed auto SDK selection changed build flags")

    with patch.dict(os.environ, {
        "WHP_MACOS_ARCH": "arm64e",
        "MACOSX_DEPLOYMENT_TARGET": "15.0",
    }):
        apple_env = {}
        sdk, arch, deployment = mod.macos_environment(apple_env)
        expected = "-arch arm64e -isysroot /mock/MacOSX.sdk -mmacosx-version-min=15.0"
        if (arch != "arm64e" or deployment != "15.0" or
            apple_env.get("CFLAGS") != expected or
            apple_env.get("LDFLAGS") != expected):
            raise SystemExit("error: sed explicit arm64e flags are inconsistent")

    with patch.dict(os.environ, {
        "WHP_MACOS_ARCH": "arm64e",
        "MACOSX_DEPLOYMENT_TARGET": "invalid",
    }):
        try:
            mod.macos_environment({})
        except RuntimeError as exc:
            if "invalid macOS deployment target" not in str(exc):
                raise
        else:
            raise SystemExit("error: malformed deployment target was accepted")


# Autopoint may be installed in a gettext keg without system aclocal macros.
# GNU sed must instead validate the staged m4/gettext.m4 copied at bootstrap.
with tempfile.TemporaryDirectory(prefix="whp-sed-gettext-") as td:
    root = pathlib.Path(td)
    keg = root / "Cellar" / "gettext" / "1.0"
    bin_dir = keg / "bin"
    bin_dir.mkdir(parents=True)
    autopoint = bin_dir / "autopoint"
    autopoint.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
    autopoint.chmod(0o755)

    if mod.gettext_aclocal_dir(str(autopoint)) != "":
        raise SystemExit("error: nonexistent system gettext macro dir was accepted")

    staged = root / "sed-source"
    (staged / "m4").mkdir(parents=True)
    try:
        mod.require_staged_gettext_macro(staged)
    except RuntimeError as exc:
        if "m4/gettext.m4" not in str(exc):
            raise
    else:
        raise SystemExit("error: unstaged gettext macro was accepted")
    (staged / "m4" / "gettext.m4").write_text(
        "dnl staged by autopoint\\n", encoding="utf-8"
    )
    mod.require_staged_gettext_macro(staged)

    aclocal = keg / "share" / "aclocal"
    aclocal.mkdir(parents=True)
    (aclocal / "gettext.m4").write_text(
        "dnl external gettext macro\\n", encoding="utf-8"
    )
    if mod.gettext_aclocal_dir(str(autopoint)) != str(aclocal):
        raise SystemExit("error: adjacent gettext macro dir was not recognized")

    # Resolve without losing a Homebrew-style prefix-side macro directory.
    prefix = root / "prefix"
    prefix_bin = prefix / "bin"
    prefix_bin.mkdir(parents=True)
    link = prefix_bin / "autopoint"
    link.symlink_to(autopoint)
    prefix_aclocal = prefix / "share" / "aclocal"
    prefix_aclocal.mkdir(parents=True)
    (prefix_aclocal / "gettext.m4").write_text(
        "dnl prefix gettext macro\\n", encoding="utf-8"
    )
    if mod.gettext_aclocal_dir(str(link)) != str(prefix_aclocal):
        raise SystemExit("error: gettext macro prefix symlink was ignored")

print("GNU sed version, gettext and compiler staging policy: verified")
