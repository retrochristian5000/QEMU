#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Validate native driver selection and preprocessing-only host CPP handoff."""

from __future__ import annotations

import os
from pathlib import Path
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
ENTRY = ROOT / "build.sh"
ADAPTER = ROOT / "seeds/cpp.sh"


def test_launcher_contract() -> None:
    text = ENTRY.read_text(encoding="utf-8")
    start = text.index("# Lock the native C preprocessor")
    end = text.index("# Resolve a native relocatable linker", start)
    section = text[start:end]
    assert "WHP_CPP_SEED=$CPP_FOR_BUILD" in section
    assert "CPP_FOR_BUILD=$WHP_CPP_ADAPTER" in section
    assert section.index("WHP_CPP_SEED=$CPP_FOR_BUILD") < section.index(
        'WHP_CPP_SEED=$("$WHP_CPP_ADAPTER" --print-seed)'
    )
    assert 'export WHP_CPP_SEED WHP_CPP_LOCKED CPP_FOR_BUILD' in section
    assert "CPP (the target" in section


def test_driver_invocation() -> None:
    # The locked path is a hot path: use a recording fake driver to prove
    # that the bridge inserts -E without invoking the C compiler for linking.
    # It is deliberately *not* a substitute for native compiler admission.
    with tempfile.TemporaryDirectory(prefix="whp-cpp-contract-") as tmp:
        path = Path(tmp)
        driver = path / "recording-clang"
        record = path / "args"
        driver.write_text(
            "#!/bin/sh\n"
            'printf "%s\\n" "$@" > "$WHP_CPP_RECORD"\n'
            'case " $* " in *" -E "*) ;; *) exit 40 ;; esac\n'
            "printf 'preprocessed\\n'\n",
            encoding="utf-8",
        )
        driver.chmod(0o755)
        env = os.environ.copy()
        env.update({
            "WHP_CPP_LOCKED": "1",
            "WHP_CPP_SEED": str(driver),
            "WHP_CPP_RECORD": str(record),
        })
        for args in (("-P", "-x", "c", "-"), ("-DVALUE=42", "source.c")):
            result = subprocess.run(
                ["/bin/sh", str(ADAPTER), *args],
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            assert result.returncode == 0, result.stderr
            assert result.stdout.strip() == "preprocessed"
            passed = record.read_text(encoding="utf-8").splitlines()
            if passed[0] == "-isysroot":
                assert len(passed) >= 3 and passed[1], passed
                passed = passed[2:]
            assert passed[0] == "-E", passed
            assert passed[1:] == list(args), passed

    text = ADAPTER.read_text(encoding="utf-8")
    assert 'exec "$driver" -isysroot "$sdk" -E "$@"' in text
    assert 'exec "$driver" -E "$@"' in text
    assert "cpp_semantic_probe()" in text
    assert '"$candidate" "$@" -E -P -x c -' in text


if __name__ == "__main__":
    test_launcher_contract()
    test_driver_invocation()
    print("native host CPP compiler-driver handoff: verified")
