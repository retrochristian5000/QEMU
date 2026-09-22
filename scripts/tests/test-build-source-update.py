#!/usr/bin/env python3
"""Guard build.sh source-refresh policy."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build.sh"
UPDATE = ROOT / "scripts" / "whp-build" / "update-source.sh"

build = BUILD.read_text(encoding="utf-8")
update = UPDATE.read_text(encoding="utf-8")
errors: list[str] = []

for script in (BUILD, UPDATE):
    proc = subprocess.run(
        ["/bin/sh", "-n", str(script)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if proc.returncode:
        errors.append(f"{script.relative_to(ROOT)} is not valid POSIX shell: {proc.stderr}")

required_build = (
    "WHP_SOURCE_UPDATE=${WHP_SOURCE_UPDATE:-auto}",
    '/bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"',
    'WHP_SOURCE_UPDATE_DONE=1',
    'exec "$SOURCE_DIR/build.sh" "$@"',
    'WHP_SOURCE_REVISION_BEFORE',
    'WHP_SOURCE_REVISION_AFTER',
)
for needle in required_build:
    if needle not in build:
        errors.append(f"build.sh source refresh contract missing: {needle}")

# Refresh must happen before Python/toolchain discovery so a newly pulled
# launcher can re-exec before mixing old and new orchestration code.
refresh_index = build.find('/bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"')
python_index = build.find("whp_python_usable()")
if refresh_index < 0 or python_index < 0 or refresh_index >= python_index:
    errors.append("source refresh must precede Python/toolchain discovery")

required_update = (
    "git -C \"$SOURCE_DIR\" pull --ff-only --recurse-submodules=no",
    "git -C \"$SOURCE_DIR\" submodule sync --recursive",
    "git -C \"$SOURCE_DIR\" submodule update --init --recursive",
    "git -C \"$SOURCE_DIR\" diff --quiet --ignore-submodules=all --",
    "git -C \"$SOURCE_DIR\" diff --cached --quiet --ignore-submodules=all --",
    "tracked submodule changes prevent a safe submodule refresh",
)
for needle in required_update:
    if needle not in update:
        errors.append(f"update-source.sh safety contract missing: {needle}")

for forbidden in (
    "submodule update --remote",
    "reset --hard",
    "clean -fd",
    "clean -fdx",
    "pull --rebase",
):
    if forbidden in update:
        errors.append(f"source refresh must not use destructive/drifting command: {forbidden}")

if "WHP_SOURCE_UPDATE must be auto, 0, or 1" not in build:
    errors.append("build.sh must validate WHP_SOURCE_UPDATE")
if "WHP_SOURCE_UPDATE must be auto, 0, or 1" not in update:
    errors.append("update-source.sh must validate WHP_SOURCE_UPDATE")
if "WHP source update: skipped under CI" not in update:
    errors.append("automatic source refresh must remain side-effect free under CI")
if "menuconfig) WHP_SOURCE_UPDATE_SKIP=1" not in build:
    errors.append("automatic source refresh must not make menuconfig a network operation")
for probe in (
    "WHP_SHELL_PROBE_ONLY",
    "WHP_BUILD_DIR_PROBE_ONLY",
    "WHP_PORTABLE_PROBE_ONLY",
):
    if probe not in build:
        errors.append(f"automatic source refresh must preserve probe purity: {probe}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("build source-update contract: verified")
