#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise native LLVM C++ standard selection with a fake Clang++ driver."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts/bootstrap-native-clang.bash"


def extract_function(text, name):
    start = text.index(f"{name}()\n{{")
    end = text.index("\n}\n", start) + len("\n}\n")
    return text[start:end]


def run_probe(function, command, compiler, log, *, host_os="macos", arch="arm64e"):
    program = "\n".join([
        'set -e',
        f'bootstrap_cxx="{compiler}"',
        f'bootstrap_cc="{compiler}"',
        f'host_os="{host_os}"',
        f'darwin_cmake_arch="{arch}"',
        'sdkroot="/fake/MacOSX.sdk"',
        'deployment_target=15.0',
        function,
        command,
    ])
    return subprocess.run(
        ["bash", "-c", program],
        text=True,
        capture_output=True,
        env={**os.environ, "WHP_FLAG_PROBE_LOG": str(log)},
        check=False,
    )


def calls(log):
    return [json.loads(line) for line in log.read_text().splitlines()]


text = BOOTSTRAP.read_text(encoding="utf-8")
std_probe = extract_function(text, "compiler_supports_cxx_standard")

with tempfile.TemporaryDirectory(prefix="whp-cxx-flags-") as tmp:
    fake = Path(tmp) / "fake-clangxx"
    log = Path(tmp) / "flags.jsonl"
    fake.write_text("""#!/usr/bin/env python3
import json
import os
from pathlib import Path
import sys

args = sys.argv[1:]
source = sys.stdin.read()
log = Path(os.environ['WHP_FLAG_PROBE_LOG'])
with log.open('a') as f:
    f.write(json.dumps({'args': args, 'source': source}) + '\\n')

if '-std=c++26' in args:
    sys.exit(1)  # Older Clang uses the c++2c spelling.
if '-std=c++2c' in args:
    # Simulate an otherwise permissive driver; inspect the full probe source.
    valid = '__cplusplus < 202400L' in source and '-arch' in args
    sys.exit(0 if valid else 1)
if '-std=c++23' in args:
    sys.exit(0)
sys.exit(1)
""", encoding="utf-8")
    fake.chmod(0o755)

    result = run_probe(std_probe, "compiler_supports_cxx_standard 26",
                       fake, log)
    assert result.returncode == 0, result.stderr
    observed = calls(log)
    assert len(observed) == 2
    assert "-std=c++26" in observed[0]["args"]
    assert "-std=c++2c" in observed[1]["args"]
    assert "__cplusplus < 202400L" in observed[1]["source"]
    assert "-arch" in observed[1]["args"]
    assert "-isysroot" in observed[1]["args"]

    log.unlink()
    result = run_probe(std_probe, "compiler_supports_cxx_standard 23",
                       fake, log)
    assert result.returncode == 0, result.stderr
    assert len(calls(log)) == 1
    assert "-std=c++23" in calls(log)[0]["args"]

print("native LLVM Clang++ language standard probes: verified")
