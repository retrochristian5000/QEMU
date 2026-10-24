#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regress Bash startup contamination of native LLVM host dependency checks."""
import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
path = ROOT / "scripts/ensure-bash.py"
host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text()
wrapper = (ROOT / "scripts/bootstrap-native-clang.sh").read_text()
llvm = (ROOT / "scripts/bootstrap-native-clang.bash").read_text()
spec = importlib.util.spec_from_file_location("whp_ensure_bash_test", path)
assert spec and spec.loader
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)
bash = shutil.which("bash")
assert bash, "Bash is required for the native LLVM shell regression"
start = host_tools.index("whp_bash_usable()\n{")
end = host_tools.index('\n}\n\nif [ -z "$WHP_BUILD_BASH" ]', start) + 2
function = host_tools[start:end]
assert "process-substitution" in function
assert "whp_probe_array=(one two)" in function
assert "env -u BASH_ENV" in function
assert "env -u BASH_ENV" in wrapper

with tempfile.TemporaryDirectory(prefix="whp-llvm-bash-") as tmp:
    root = Path(tmp)
    hook = root / "startup.sh"
    hook.write_text("exit 79\n")
    tainted = os.environ.copy()
    # Make the negative control deterministic on developer machines where
    # inherited POSIX options would otherwise suppress BASH_ENV execution.
    for key in ("POSIXLY_CORRECT", "SHELLOPTS", "BASHOPTS"):
        tainted.pop(key, None)
    tainted.update(BASH_ENV=str(hook), ENV=str(hook))
    # In POSIX mode Bash can ignore BASH_ENV. Reproduce the regular Bash
    # startup failure first; test the POSIXLY_CORRECT contaminant separately.
    negative = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", "exit 0"],
        env=tainted, capture_output=True, check=False
    )
    assert negative.returncode == 79, negative.returncode
    tainted["POSIXLY_CORRECT"] = "y"
    with mock.patch.dict(os.environ, tainted, clear=True):
        clean = helper.bash_probe_env()
        assert not set(helper.BASH_PROBE_ENV_VARS).intersection(clean)
        assert helper.bash_usable(Path(bash))
        assert helper.bash_machtype(Path(bash))

    # The caller starts clean and exports BASH_ENV only before invoking the
    # candidate. This tests the production host-tools function itself.
    env = os.environ.copy()
    for key in ("BASH_ENV", "ENV", "POSIXLY_CORRECT", "SHELLOPTS", "BASHOPTS"):
        env.pop(key, None)
    script = (function + "\n" +
              'export BASH_ENV="$1" ENV="$1" POSIXLY_CORRECT=y\n' +
              'whp_bash_usable "$2"\n')
    good = subprocess.run([bash, "-c", script, "--", str(hook), bash],
                          env=env, capture_output=True, text=True)
    assert good.returncode == 0, good.stderr
    fake = root / "version-only-bash"
    fake.write_text("#!/bin/sh\ncase \"$*\" in\n"
                    "  *process-substitution*) exit 37 ;;\n"
                    "  *) exit 0 ;;\nesac\n")
    fake.chmod(0o755)
    weak = subprocess.run(
        [bash, "-c", script, "--", str(hook), str(fake)],
        env=env, capture_output=True, text=True
    )
    assert weak.returncode != 0, "version-only shell passed feature check"

    # Full real POSIX wrapper, but replace the expensive LLVM compilation
    # with a prebuilt fixture prefix. An injected Bash startup exit must
    # not stop the .bash implementation from returning its prefix.
    directory = root / "scripts"
    directory.mkdir()
    (directory / "bootstrap-native-clang.sh").write_text(wrapper)
    (directory / "bootstrap-native-clang.bash").write_text(
        '#!/usr/bin/env bash\n'
        'test -z "$BASH_ENV" || exit 71\n'
        'printf "%s\\n" "$WHP_TEST_PREFIX"\n'
    )
    prefix = root / "toolchain"
    bin_dir = prefix / "bin"
    bin_dir.mkdir(parents=True)
    for name in ("clang", "clang++", "llvm-ar", "llvm-ranlib", "llvm-nm",
                 "llvm-objcopy", "llvm-objdump", "llvm-readelf",
                 "llvm-strip", "llvm-lipo", "ld64.lld"):
        exe = bin_dir / name
        exe.write_text("#!/bin/sh\nexit 0\n")
        exe.chmod(0o755)
    (prefix / "lib").mkdir()
    (prefix / "lib/libLTO.dylib").write_bytes(b"fixture")
    # Keep ordinary noninteractive Bash mode here so BASH_ENV actually
    # executes if the launcher ever loses its startup isolation.
    tainted.pop("POSIXLY_CORRECT", None)
    tainted.update(WHP_BUILD_BASH=bash, WHP_TEST_PREFIX=str(prefix))
    wrapped = subprocess.run(
        ["/bin/sh", str(directory / "bootstrap-native-clang.sh")],
        env=tainted, capture_output=True, text=True
    )
    assert wrapped.returncode == 0, wrapped.stderr
    assert wrapped.stdout.strip() == str(prefix), wrapped.stdout

for option in ("-DLLVM_ENABLE_ZLIB=OFF", "-DLLVM_ENABLE_ZSTD=OFF",
               "-DLLVM_ENABLE_LIBEDIT=OFF", "-DLLDB_ENABLE_PYTHON=OFF",
               "-DLLDB_ENABLE_LZMA=OFF"):
    assert option in llvm, option

print("native LLVM Bash startup and dependency boundary: verified")
