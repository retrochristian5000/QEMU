#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard tracked seed modes and POSIX interpreter execution boundaries.

This test is intentionally cheap: it does not bootstrap any toolchain.
Shell grammar is covered by test-shell-dialect-contract.py.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess

ROOT = Path(__file__).resolve().parents[2]
NONEXECUTABLE_PROBES = {
    "GNUar.sh": ("--whp-gnu-ar-adapter-probe", "whp-qemu-gnu-ar-seed-adapter"),
    "[.sh": ("--whp-bracket-adapter-probe", "whp-qemu-bracket-seed-adapter"),
    "ar.sh": ("--whp-ar-adapter-probe", "whp-qemu-ar-seed-adapter"),
    "autoconf.sh": ("--whp-autoconf-adapter-probe", "whp-qemu-autoconf-seed-adapter"),
    "autom4te.sh": ("--whp-autom4te-adapter-probe", "whp-qemu-autom4te-seed-adapter"),
    "automake.sh": ("--whp-automake-adapter-probe", "whp-qemu-automake-seed-adapter"),
    "brew.sh": ("--whp-brew-adapter-probe", "whp-qemu-brew-seed-adapter"),
    "cargo.sh": ("--whp-cargo-adapter-probe", "whp-qemu-cargo-seed-adapter"),
    "make.sh": ("--whp-make-adapter-probe", "whp-qemu-make-seed-adapter"),
    "perl.sh": ("--whp-perl-adapter-probe", "whp-qemu-perl-seed-adapter"),
    "ranlib.sh": ("--whp-ranlib-adapter-probe", "whp-qemu-ranlib-seed-adapter"),
    "rustc.sh": ("--whp-rustc-adapter-probe", "whp-qemu-rustc-seed-adapter"),
    "xcrun.sh": ("--whp-xcrun-adapter-probe", "whp-qemu-xcrun-seed-adapter"),
    "yacc.sh": ("--whp-yacc-adapter-probe", "whp-qemu-yacc-seed-adapter"),
}

# Critical downstream edges: each 100644 seed must be executed via /bin/sh,
# never directly because its shebang does not grant executable permission.
SHELL_CALL_CONTRACTS = {
    "scripts/ensure-cmake.py": (
        "[\"/bin/sh\", str(adapter), option]",
    ),
    "scripts/ensure-sccache.py": (
        "['/bin/sh', str(ROOT / 'seeds/cargo.sh')",
        "['/bin/sh', str(ROOT / 'seeds/rustc.sh')",
    ),
    "scripts/ensure-perl.py": (
        "[\"/bin/sh\", str(ROOT / \"seeds\" / \"perl.sh\")",
        "[\"/bin/sh\", str(ROOT / \"seeds\" / \"ar.sh\")",
        "[\"/bin/sh\", str(ROOT / \"seeds\" / \"ranlib.sh\")",
    ),
    "scripts/ensure-autoconf.py": (
        "[\"/bin/sh\", str(adapter), \"--print-autotools-seed\"]",
        "[\"/bin/sh\", str(adapter), flag]",
    ),
    "scripts/ensure-automake.py": (
        "[\"/bin/sh\", str(adapter), \"--print-autotools-seed\"]",
        "[\"/bin/sh\", str(adapter), flag]",
        "[\"/bin/sh\", str(ROOT / \"seeds\" / \"automake.sh\")",
    ),
    "scripts/whp-build/native-archive-pair.sh": (
        "/bin/sh \"$root/seeds/GNUar.sh\"",
        "/bin/sh \"$root/seeds/ar.sh\"",
        "/bin/sh \"$root/seeds/ranlib.sh\"",
    ),
    "scripts/whp-build/host-tools.sh": (
        "/bin/sh \"$SOURCE_DIR/seeds/automake.sh\"",
        "/bin/sh \"$SOURCE_DIR/seeds/autoconf.sh\"",
        "/bin/sh \"$SOURCE_DIR/seeds/autom4te.sh\"",
        "/bin/sh \"$SOURCE_DIR/seeds/perl.sh\"",
    ),
    "build.sh": (
        "/bin/sh \"$SOURCE_DIR/seeds/make.sh\"",
        "/bin/sh \"$SOURCE_DIR/seeds/xcrun.sh\"",
    ),
    "scripts/bootstrap-powerpc-toolchain-git.bash": (
        "/bin/sh \"$SOURCE_DIR/seeds/yacc.sh\"",
    ),
    "seeds/yacc.sh": (
        "/bin/sh \"$seed_dir/brew.sh\"",
    ),
    "seeds/rustc.sh": (
        "/bin/sh \"$cargo_adapter\"",
    ),
    "seeds/autoconf.sh": (
        "exec /bin/sh \"$pair_seed\"",
    ),
}


def tracked_seed_modes() -> dict[str, str]:
    completed = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files", "--stage", "-z", "--", "seeds/"],
        check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
    )
    modes: dict[str, str] = {}
    for item in completed.stdout.split(b"\0"):
        if not item:
            continue
        header, path = item.split(b"\t", 1)
        mode, _sha, stage = header.decode("ascii").split()
        name = path.decode("utf-8", "surrogateescape")
        if not name.endswith(".sh"):
            continue
        if stage != "0" or name in modes:
            raise RuntimeError(f"unmerged or duplicate tracked seed: {name}")
        modes[name] = mode
    return modes


def verify_modes_and_probes() -> tuple[int, int]:
    modes = tracked_seed_modes()
    nonexec = {f"seeds/{name}" for name in NONEXECUTABLE_PROBES}
    if nonexec - modes.keys():
        raise RuntimeError(f"missing tracked nonexecutable seeds: {sorted(nonexec - modes.keys())}")
    observed = {name for name, mode in modes.items() if mode == "100644"}
    if observed != nonexec:
        raise RuntimeError(
            "nonexecutable seed set changed without a call-site audit: "
            f"added={sorted(observed - nonexec)} removed={sorted(nonexec - observed)}"
        )

    for name, mode in sorted(modes.items()):
        if mode not in ("100644", "100755"):
            raise RuntimeError(f"invalid seed Git mode {name}: {mode}")
        path = ROOT / name
        if path.is_symlink() or not path.is_file():
            raise RuntimeError(f"seed checkout is missing or symlinked: {name}")
        is_executable = bool(path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))
        if is_executable != (mode == "100755"):
            raise RuntimeError(f"seed checkout permission differs from Git: {name} ({mode})")
        if path.read_text(encoding="utf-8").splitlines()[0] != "#!/bin/sh":
            raise RuntimeError(f"seed must have POSIX sh shebang: {name}")

    # Probe each nonexecutable script through its actual interpreter. These
    # probes must run before any Homebrew, macOS, archiver or Rust discovery.
    for filename, (flag, expected) in NONEXECUTABLE_PROBES.items():
        path = ROOT / "seeds" / filename
        result = subprocess.run(
            ["/bin/sh", str(path), flag],
            env={"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C"},
            text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            check=False, timeout=10,
        )
        if result.returncode or result.stdout != expected + "\n":
            raise RuntimeError(
                f"POSIX seed probe failed: {filename} ({result.returncode}): "
                f"{result.stderr.strip() or result.stdout.strip()}"
            )
    return len(modes), len(nonexec)


def verify_interpreter_call_sites() -> None:
    for filename, patterns in SHELL_CALL_CONTRACTS.items():
        source = (ROOT / filename).read_text(encoding="utf-8")
        for pattern in patterns:
            if pattern not in source:
                raise RuntimeError(
                    f"{filename} no longer uses the approved interpreter boundary: {pattern}"
                )


def main() -> int:
    total, nonexec = verify_modes_and_probes()
    verify_interpreter_call_sites()
    print(
        f"WHP seed permissions: {total} tracked POSIX seeds, "
        f"{nonexec} nonexecutable adapter probes and shell handoffs verified"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
