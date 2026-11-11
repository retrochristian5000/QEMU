#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Hermetic seed-compiler NEON resource-header admission regression."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BOOTSTRAP = ROOT / "scripts" / "bootstrap-native-clang.bash"


def function_source(name):
    script = BOOTSTRAP.read_text(encoding="utf-8")
    start = script.index(name + "()\n{")
    end = script.index("\n}\n", start) + len("\n}\n")
    return script[start:end]


def run_probe(function, compiler, environ, language="c"):
    program = "\n".join([
        "set -e",
        "darwin_cmake_arch=arm64e",
        "sdkroot=/fake/MacOSX.sdk",
        "deployment_target=15.0",
        function,
        f'macos_seed_has_neon "{compiler}" "{language}"',
    ])
    return subprocess.run(
        ["bash", "-c", program], env=environ, capture_output=True,
        text=True, check=False,
    )


with tempfile.TemporaryDirectory(prefix="whp-native-neon-seed-") as temporary:
    root = Path(temporary)
    resource = root / "resources"
    headers = resource / "include"
    headers.mkdir(parents=True)
    fake = root / "clang"
    fake.write_text("""#!/usr/bin/env python3
import os
from pathlib import Path
import sys

args = sys.argv[1:]
if args == ['-print-resource-dir']:
    print(os.environ['WHP_NEON_TEST_RESOURCE'])
    sys.exit(0)
source = sys.stdin.read()
valid = all((
    '-arch' in args,
    'arm64e' in args,
    '-isysroot' in args,
    '/fake/MacOSX.sdk' in args,
    '-Werror' in args,
    '-fsyntax-only' in args,
    '#include <arm_neon.h>' in source,
    'veorq_u8(a, b)' in source,
    os.environ.get('CPATH') is None,
))
sys.exit(0 if valid else 1)
""", encoding="utf-8")
    fake.chmod(0o755)
    env = {
        **os.environ, "WHP_NEON_TEST_RESOURCE": str(resource),
        "CPATH": "/poison/target/headers",
    }
    probe = function_source("macos_seed_has_neon")
    assert run_probe(probe, fake, env).returncode != 0, (
        "missing compiler resource header was accepted"
    )
    (headers / "arm_neon.h").write_text("/* generated fixture */\n", encoding="utf-8")
    for language in ("c", "c++"):
        result = run_probe(probe, fake, env, language)
        assert result.returncode == 0, (language, result.stderr)
    (headers / "arm_neon.h").unlink()
    assert run_probe(probe, fake, env).returncode != 0

bootstrap = BOOTSTRAP.read_text(encoding="utf-8")
assert bootstrap.index("macos_seed_has_neon()") < bootstrap.index(
    'cmake --build "$LLVM_BUILD_DIR" --target distribution'
)
assert bootstrap.index("native_neon_headers_usable()") < bootstrap.index(
    'if [[ "$TOOLCHAIN_FORCE_REBUILD" == 0'
)
assert 'native_neon_headers_usable "$prefix" || return 1' in bootstrap
print("native LLVM seed NEON header admission: verified")
