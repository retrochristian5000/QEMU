#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify native LLD C++ links and isolate optional worker flags from configure."""

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
BUILDER = ROOT / "scripts/macos-builder.bash"
BOOTSTRAP = ROOT / "scripts/bootstrap-native-clang.bash"
builder = BUILDER.read_text(encoding="utf-8")
bootstrap = BOOTSTRAP.read_text(encoding="utf-8")

# Keep native LLD selected only after a clean C++ link. No optional input
# worker setting may enter native LLVM CMake or QEMU's global LDFLAGS.
assert "bootstrap_lld_link_probe()\n{" in bootstrap
assert "if bootstrap_lld_link_probe; then" in bootstrap
assert "--read-workers" not in bootstrap
assert '"-DLLVM_PARALLEL_LINK_JOBS=$LLVM_LINK_JOBS"' in bootstrap
assert 'whp_native_lld_accepts_read_workers' not in builder
assert 'whp_append_flag LDFLAGS "-Wl,--read-workers=' not in builder
assert 'global LDFLAGS during QEMU configure' in builder

start = bootstrap.index("bootstrap_lld_link_probe()\n{")
end = bootstrap.index("\n}\n", start) + len("\n}\n")
base_link_probe = bootstrap[start:end]

start = builder.index("validate_macho_thread_flags()\n{")
end = builder.index("\n}\n", start) + len("\n}\n")
validate_flags = builder[start:end]

with tempfile.TemporaryDirectory(prefix="whp-native-lld-cxx-") as temp:
    folder = Path(temp)
    log = folder / "calls.log"
    driver = folder / "fake-cxx"
    driver.write_text(r"""#!/bin/sh
printf '%s\n' "$*" >> "$WHP_DRIVER_LOG"
case " $* " in *' -Wl,--read-workers='*) exit 12 ;; esac
case " $* " in *' -arch arm64e '*) ;; *) exit 2 ;; esac
case " $* " in *' -isysroot /fake/MacOSX.sdk '*) ;; *) exit 3 ;; esac
case " $* " in *' -mmacosx-version-min=15.0 '*) ;; *) exit 4 ;; esac
case " $* " in *' -fuse-ld=lld '*) ;; *) exit 5 ;; esac
case " $* " in *' -x c++ '*) ;; *) exit 6 ;; esac
if [ "$WHP_DRIVER_REJECT" = 1 ]; then exit 7; fi
if [ "$WHP_DRIVER_WARN" = 1 ]; then
    printf 'ld: warning: incompatible linker\n' >&2
fi
if [ "$WHP_DRIVER_SKIP_OUTPUT" = 1 ]; then exit 0; fi
output=
previous=
for arg do
    if [ "$previous" = -o ]; then output=$arg; break; fi
    previous=$arg
done
[ -n "$output" ] || exit 8
printf '#!/bin/sh\nexit 0\n' > "$output"
chmod +x "$output"
exit 0
""", encoding="utf-8")
    driver.chmod(0o755)

    script = "\n".join([
        "set -e",
        f'bootstrap_cxx="{driver}"',
        f'TOOLCHAIN_DIR="{folder}"',
        "darwin_cmake_arch=arm64e",
        "sdkroot=/fake/MacOSX.sdk",
        "deployment_target=15.0",
        base_link_probe,
        "bootstrap_lld_link_probe",
    ])
    base_env = {**os.environ, "WHP_DRIVER_LOG": str(log)}
    for name, extra, expected in (
        ("normal", {}, True),
        ("unsupported-driver", {"WHP_DRIVER_REJECT": "1"}, False),
        ("missing-linked-output", {"WHP_DRIVER_SKIP_OUTPUT": "1"}, False),
        ("warning-treated-as-failure", {"WHP_DRIVER_WARN": "1"}, False),
    ):
        if log.exists():
            log.unlink()
        result = subprocess.run(
            ["bash", "-c", script], env={**base_env, **extra},
            text=True, capture_output=True, check=False,
        )
        assert (result.returncode == 0) == expected, (
            name, result.returncode, result.stderr
        )
        calls = log.read_text(encoding="utf-8").splitlines()
        assert len(calls) == 1, (name, calls)
        assert "--read-workers" not in calls[0], (name, calls)

    # Execute the QEMU wrapper's real input validation, not a reimplementation.
    # A perfectly valid LLD must not authorize --read-workers inside global
    # configure flags; normal -Wl,--threads=2 remains a separate contract.
    validate_script = "\n".join([
        "set -e",
        'NATIVE_LLVM_DIR="/fake/native-llvm"',
        'LD="/fake/native-llvm/bin/ld64.lld"',
        'NATIVE_LLVM_LDFLAG=-fuse-ld=lld',
        "whp_native_lld_accepts_threads() { return 0; }",
        validate_flags,
        "validate_macho_thread_flags",
    ])
    for value, accepted in (
        ("", True),
        ("-Wl,--read-workers=2", False),
        ("-Xlinker --read-workers=2", False),
        ("--read-workers=2", False),
        ("-Wl,--threads=2", True),
    ):
        result = subprocess.run(
            ["bash", "-c", validate_script],
            env={**os.environ, "LDFLAGS": value},
            capture_output=True, text=True, check=False,
        )
        assert (result.returncode == 0) == accepted, (
            value, result.returncode, result.stderr
        )
        if not accepted:
            assert "cannot appear in global LDFLAGS" in result.stderr

print("Mach-O LLD Clang++ and configure flag isolation: verified")
