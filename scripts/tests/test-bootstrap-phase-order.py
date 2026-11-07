#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[2]
build = (ROOT / "build.sh").read_text(encoding="utf-8")
host_libraries = (ROOT / "scripts/whp-build/host-libraries.sh").read_text(
    encoding="utf-8"
)
host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
    encoding="utf-8"
)

def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")

require(
    host_libraries,
    "whp_prepare_bootstrap_zlib()",
    "bootstrap zlib phase helper definition",
)
require(
    host_libraries,
    "whp_prepare_qemu_host_libraries()",
    "host-library phase helper definition",
)
require(
    build,
    '. "$SOURCE_DIR/scripts/whp-build/host-libraries.sh"',
    "host-library phase module load",
)
require(
    build,
    'if [ "$BOOTSTRAP_NATIVE_LLVM" = 0 ]; then\n    whp_prepare_qemu_host_libraries',
    "non-LLVM early host-library path",
)
require(
    build,
    'if [ "$BOOTSTRAP_NATIVE_LLVM" = 1 ]; then\n    # These libraries are linked into QEMU itself.',
    "LLVM deferred host-library path",
)

library_module = build.index(
    '. "$SOURCE_DIR/scripts/whp-build/host-libraries.sh"'
)
tool_module = build.index(
    '. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"'
)
if not library_module < tool_module:
    raise SystemExit(
        "error: host-library helper definitions must load before host-tool execution"
    )

# Schedule independent, small host dependencies before larger Autotools and
# Bash trees, but never move a consumer before the tools needed to build it.
# Seed Git is selected by build.sh ahead of the parent source updater;
# host-tools only consumes the already validated choice.
seed_git_hook = build.index('WHP_GIT_SEED=$("$SOURCE_DIR/seeds/git.sh" --print-seed)')
source_update_hook = build.index(
    '/bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"'
)
late_git_hook = build.index(
    '. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"'
)
require(
    build, 'WHP_GIT_SEED=$("$SOURCE_DIR/seeds/git.sh" --print-seed) || return 1',
    "Git seed fail-closed selection",
)
require(
    build,
    "printf 'QEMU seed git: %s\\n' \"$WHP_GIT_SEED\" >&2",
    "Git seed diagnostic",
)
require(
    host_tools, 'WHP_GIT_SEED_SELECTED:-0',
    "host tools consume one already validated seed Git",
)
if 'git.sh" --print-seed' in host_tools:
    raise SystemExit("error: Git seed selected twice in host tools")
if not seed_git_hook < source_update_hook < late_git_hook:
    raise SystemExit("error: Git seed must be selected before source updater")
zlib_hook = host_tools.index("whp_prepare_bootstrap_zlib")
automake_hook = host_tools.index("scripts/ensure-automake.py")
autoconf_hook = host_tools.index("scripts/ensure-autoconf.py")
make_hook = host_tools.index("scripts/ensure-make.py")
sed_hook = host_tools.index("scripts/ensure-sed.py")
git_hook = host_tools.index("scripts/ensure-git.py")
ninja_hook = host_tools.index("scripts/ensure-ninja.py")
bash_hook = host_tools.index("scripts/ensure-bash.py")

if not (
    zlib_hook
    < automake_hook
    < autoconf_hook
    < make_hook
    < sed_hook
    < git_hook
    < ninja_hook
    < bash_hook
):
    raise SystemExit(
        "error: expected bootstrap-zlib -> Automake -> Autoconf -> "
        "Make -> sed -> managed Git -> Ninja -> Bash pre-LLVM order"
    )
if host_tools.count("whp_prepare_bootstrap_zlib") != 1:
    raise SystemExit("error: bootstrap zlib must have exactly one host-tool call")
if host_tools.count("scripts/ensure-ninja.py") != 2:
    raise SystemExit("error: Ninja should have one resolver stage with two fallbacks")

# Early zlib must stay on the seed GNU Make/C toolchain; the two roles are
# separate so native LLVM does not retroactively change Git's zlib ABI.
require(
    host_libraries,
    '--role bootstrap --cc "$CC_FOR_BUILD"',
    "zlib build-machine compiler admission before managed Make",
)
require(
    build,
    'export WHP_MAKE_SEED MAKE_CMD MAKE',
    "seed Make must exist before host-tool execution",
)
require(
    build,
    'export CC_FOR_BUILD',
    "native C seed must exist before host-tool execution",
)

# Log labels describe the generic tool role, not the selected implementation.
for label in ("awk", "grep", "sed", "make", "cc", "ld"):
    require(build, f"QEMU seed {label}:", f"{label} seed diagnostic")
for previous in (
    "QEMU seed AWK:", "QEMU seed GNU Make:",
    "QEMU bootstrap C compiler:", "QEMU bootstrap native linker:",
):
    if previous in build:
        raise SystemExit(f"error: obsolete seed diagnostic: {previous}")
require(
    host_tools, "QEMU make: WHP managed",
    "generic managed Make diagnostic",
)

artifact_zlib_hook = host_libraries.index("whp_prepare_zlib_phase artifact")
sdl_hook = host_libraries.index("BOOTSTRAP_SDL=")
if not artifact_zlib_hook < sdl_hook:
    raise SystemExit("error: artifact zlib must be resolved before SDL/JACK")

llvm_hook = build.index('scripts/bootstrap-native-clang.sh')
deferred_comment = build.index(
    "These libraries are linked into QEMU itself. Build them only after"
)
libtool_hook = build.index("scripts/ensure-libtool.py")
libisofs_hook = build.index("scripts/ensure-libisofs.py")

if not llvm_hook < deferred_comment < libtool_hook < libisofs_hook:
    raise SystemExit(
        "error: expected LLVM -> deferred SDL/JACK -> Libtool -> libisofs order"
    )

sdl = (ROOT / "scripts/ensure-sdl.py").read_text(encoding="utf-8")
require(sdl, 'for env_name in ("CC", "CC_FOR_BUILD")', "SDL compiler priority")

jack = (ROOT / "scripts/ensure-jack.py").read_text(encoding="utf-8")
require(jack, 'command_path("clang", "CC"', "JACK artifact C compiler")
require(jack, 'command_path("clang++", "CXX"', "JACK artifact C++ compiler")
require(jack, 'build_env = "CC_FOR_BUILD"', "JACK seed fallback")

ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
require(ledger, "Bootstrap phase ordering", "phase-order ledger")
require(ledger, "Artifact-library phase", "artifact phase ledger")

# GitHub policy rejects floating checkout tags before any bootstrap can run.
checkout_use = re.compile(r"^\s*(?:-\s*)?uses:\s*actions/checkout@([^\s#]+)", re.M)
for name in (
    "compiler-seed-adapter.yml",
    "git-bootstrap.yml",
    "windows-python-launcher.yml",
    "bundled-ninja-fallback.yml",
    "sdl-bootstrap.yml",
):
    workflow = (ROOT / ".github/workflows" / name).read_text(
        encoding="utf-8"
    )
    refs = checkout_use.findall(workflow)
    if not refs or any(not re.fullmatch(r"[a-f0-9]{40}", ref) for ref in refs):
        raise SystemExit(
            f"error: {name} must pin all actions/checkout calls to full SHAs"
        )

# Forced tool bootstraps must reject failed pinned tools before considering
# host fallback. Probe-only modes still avoid expensive bootstrap work.
for tool, helper in (
    ("AUTOMAKE", "whp_automake_pair_usable"),
    ("AUTOCONF", "whp_autoconf_pair_usable"),
):
    block_start = host_tools.index(f'if ! {helper} "${{')
    block_end = host_tools.index("    unset WHP_HOST_", block_start)
    block = host_tools[block_start:block_end]
    if block.index(f'if [ "$BOOTSTRAP_{tool}" = 1 ] &&') > block.index(
        f'elif {helper} "$WHP_HOST_'
    ):
        raise SystemExit(f"error: forced {tool} can silently use host fallback")
    for probe in ("WHP_SHELL_PROBE_ONLY", "WHP_PORTABLE_PROBE_ONLY"):
        if probe not in block:
            raise SystemExit(f"error: forced {tool} guard blocks probe-only mode")

print("WHP bootstrap phase ordering: verified")
