#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import importlib.util
import pathlib
import tempfile

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

print("GNU sed version staging policy: verified")
