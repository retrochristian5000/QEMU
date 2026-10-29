#!/usr/bin/env python3
"""Guard build.sh source-refresh policy."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build.sh"
UPDATE = ROOT / "scripts" / "whp-build" / "update-source.sh"
SHARED_SHELL = ROOT / "scripts" / "whp-build" / "shell-functions.sh"

build = BUILD.read_text(encoding="utf-8")
update = UPDATE.read_text(encoding="utf-8")
shared_shell = SHARED_SHELL.read_text(encoding="utf-8")
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
    'WHP_SOURCE_UPDATE=$(whp_require_auto_switch WHP_SOURCE_UPDATE "${WHP_SOURCE_UPDATE:-auto}")',
    '/bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"',
    'WHP_SOURCE_UPDATE_DONE=1',
    'exec "$SOURCE_DIR/build.sh" "$@"',
    'WHP_SOURCE_REVISION_BEFORE',
    'WHP_SOURCE_REVISION_AFTER',
)
for needle in required_build:
    if needle not in build:
        errors.append(f"build.sh source refresh contract missing: {needle}")

# Refresh must happen before Python/toolchain discovery so a newly updated
# launcher can re-exec before mixing old and new orchestration code.
refresh_index = build.find('/bin/sh "$SOURCE_DIR/scripts/whp-build/update-source.sh"')
python_index = build.find("whp_python_usable()")
if refresh_index < 0 or python_index < 0 or refresh_index >= python_index:
    errors.append("source refresh must precede Python/toolchain discovery")

required_update = (
    'git -C "$SOURCE_DIR" ls-remote "$remote" "$merge_ref"',
    'git -C "$SOURCE_DIR" fetch --no-tags --no-recurse-submodules',
    '"$remote" "$merge_ref:$upstream_ref"',
    'git -C "$SOURCE_DIR" merge --ff-only "$upstream_ref"',
    'git -C "$SOURCE_DIR" submodule sync --recursive',
    'upstream ref unchanged; object fetch skipped',
    'pinned submodules remain lazy',
    'reconciling existing DTC wrap',
    'scripts/ensure-dtc-subproject.py',
    'git -C "$SOURCE_DIR" diff --quiet --ignore-submodules=all --',
    'git -C "$SOURCE_DIR" diff --cached --quiet --ignore-submodules=all --',
)
for needle in required_update:
    if needle not in update:
        errors.append(f"update-source.sh download-minimization contract missing: {needle}")

for forbidden in (
    "git -C \"$SOURCE_DIR\" pull ",
    "submodule update --init --recursive",
    "submodule update --remote",
    "fetch --all",
    "fetch --tags",
    "reset --hard",
    "clean -fd",
    "clean -fdx",
    "pull --rebase",
):
    if forbidden in update:
        errors.append(f"source refresh must not use broad/destructive command: {forbidden}")

# build.sh delegates strict enum validation to the shared POSIX shell
# helper; searching for the old inline error text is an obsolete test.
if ("whp_require_auto_switch()" not in shared_shell or
        "must be auto, 0, or 1" not in shared_shell):
    errors.append("shared shell must validate auto/0/1 source-update mode")
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


# Exercise the actual source updater with a historical DTC marker.  Merely
# testing the stand-alone helper does not check that the updater invokes it.
import hashlib
import os
import shutil
import tempfile


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, check=True,
    ).stdout.strip()


def test_existing_dtc_reconciles_from_source_updater():
    with tempfile.TemporaryDirectory(prefix="whp-updater-dtc-") as tmp:
        root = Path(tmp)
        (root / "scripts" / "whp-build").mkdir(parents=True)
        shutil.copy2(UPDATE, root / "scripts/whp-build/update-source.sh")
        shutil.copy2(ROOT / "scripts/ensure-dtc-subproject.py",
                     root / "scripts/ensure-dtc-subproject.py")
        git("init", "-q", str(root))
        git("config", "user.name", "WHP Test", cwd=root)
        git("config", "user.email", "whp@example.invalid", cwd=root)
        (root / "README").write_text("parent QEMU fixture\n")
        git("add", "README", cwd=root)
        git("commit", "-qm", "QEMU source", cwd=root)

        subprojects = root / "subprojects"
        checkout = subprojects / "dtc"
        checkout.mkdir(parents=True)
        git("init", "-q", str(checkout))
        git("config", "user.name", "WHP Test", cwd=checkout)
        git("config", "user.email", "whp@example.invalid", cwd=checkout)
        (checkout / "libfdt").mkdir()
        (checkout / "meson.build").write_text(
            "project('dtc', 'c', version: files('VERSION.txt'))\n"
            "subdir('libfdt')\n"
        )
        (checkout / "libfdt/meson.build").write_text(
            "libfdt_dep = declare_dependency()\n"
        )
        (checkout / "VERSION.txt").write_text("1.6.0\n")
        (checkout / "meson_options.txt").write_text(
            "option('tools', type: 'boolean', value: true)\n"
        )
        git("add", ".", cwd=checkout)
        git("commit", "-qm", "original DTC", cwd=checkout)
        old_revision = git("rev-parse", "HEAD", cwd=checkout)

        (checkout / "VERSION.txt").write_text("1.8.1\n")
        (checkout / "meson_options.txt").write_text(
            "option('tools', type: 'boolean', value: true)\n"
            "option('yaml', type: 'feature', value: 'auto')\n"
            "option('python', type: 'feature', value: 'auto')\n"
            "option('tests', type: 'boolean', value: true)\n"
        )
        git("add", ".", cwd=checkout)
        git("commit", "-qm", "pinned DTC", cwd=checkout)
        pin = git("rev-parse", "HEAD", cwd=checkout)
        git("checkout", "--detach", old_revision, cwd=checkout)
        wrap = subprojects / "dtc.wrap"
        wrap.write_text(
            "[wrap-git]\nurl = https://example.invalid/dtc.git\n"
            f"revision = {pin}\ndepth = 1\n"
        )
        marker = checkout / ".meson-subproject-wrap-hash.txt"
        legacy = "932ca47fc50a6932207a6fc82e15d07d848e93c4ff9abcd0cc34c15f40a30885"
        marker.write_text(legacy + "\n")
        expected = hashlib.sha256(wrap.read_text().encode("utf-8")).hexdigest()
        env = os.environ.copy()
        env.pop("CI", None)  # Updater intentionally skips automatic CI refresh.
        env["WHP_SOURCE_UPDATE"] = "auto"
        env["PYTHON"] = sys.executable
        cmd = ["/bin/sh", str(root / "scripts/whp-build/update-source.sh")]
        first = subprocess.run(cmd, cwd=root, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True)
        assert "reconciling existing DTC wrap" in first.stderr, first.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == pin
        assert marker.read_text().strip() == expected
        assert marker.read_text().strip() != legacy

        second = subprocess.run(cmd, cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
        assert "reconciling existing DTC wrap" in second.stderr, second.stderr
        assert marker.read_text().strip() == expected

        # Explicit opt-out must remain inert even if the old marker returns.
        marker.write_text(legacy + "\n")
        env["WHP_SOURCE_UPDATE"] = "0"
        subprocess.run(cmd, cwd=root, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert marker.read_text().strip() == legacy


try:
    test_existing_dtc_reconciles_from_source_updater()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"DTC source-update integration: {exc}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("build source-update contract: verified")
