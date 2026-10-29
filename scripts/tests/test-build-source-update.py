#!/usr/bin/env python3
"""Guard build.sh source-refresh policy."""

from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build.sh"
CONFIGURE = ROOT / "configure"
UPDATE = ROOT / "scripts" / "whp-build" / "update-source.sh"
SHARED_SHELL = ROOT / "scripts" / "whp-build" / "shell-functions.sh"

build = BUILD.read_text(encoding="utf-8")
configure = CONFIGURE.read_text(encoding="utf-8")
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
    'DTC is reconciled by build.sh after the selected Python and Git bootstrap',
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

# Parent fast-forward stays first; DTC reconciliation runs only after
# selected host Git/Python and menuconfig have been loaded.
host_index = build.find('. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"')
dtc_index = build.find("# WHP DTC post-host bootstrap reconciliation")
config_index = build.find('eval "$WHP_CONFIG_ENV"')
portable_index = build.find('portable_core()')
if not (refresh_index < python_index < config_index < host_index <
        dtc_index < portable_index):
    errors.append("DTC reconciliation must follow config and host tool selection")
if 'scripts/ensure-dtc-subproject.py' in update:
    errors.append("early source updater must not reconcile DTC before host tools")

# A system libfdt selection must bypass DTC in BOTH entry points. It must
# continue into Meson rather than dying inside the DTC diagnosis helper.
post_dtc = build[dtc_index:portable_index]
for guard in (
    '[ "${QEMU_FDT_MODE:-auto}" != system ]',
    '[ "${QEMU_FDT_MODE:-auto}" != disabled ]',
):
    if guard not in post_dtc:
        errors.append(f"post-host-tools DTC path missing provider guard: {guard}")
if not (
    'fdt_provider=auto' in configure and
    '-Dfdt=*) fdt_provider="$optarg"' in configure and
    '--disable-fdt) fdt_provider=disabled' in configure and
    '--enable-fdt=*) fdt_provider="$optarg"' in configure
):
    errors.append("configure must track the effective fdt selection")
if not (
    'if test "$fdt_provider" = system || test "$fdt_provider" = disabled; then'
    in configure
):
    errors.append("configure must bypass DTC for system/disabled libfdt")

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


# Exercise the two real execution phases using a historical DTC marker:
# parent refresh must not touch DTC, and the extracted post-host-tools block
# must use the exact promoted GIT/PYTHON without rebuilding or resetting.
import hashlib
import os
import shutil
import tempfile


def git(*args, cwd=None):
    return subprocess.run(
        ["git", *args], cwd=cwd, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, text=True, check=True,
    ).stdout.strip()


def test_dtc_reconciles_after_host_tools():
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
        # A parent source refresh must leave the old DTC commit/marker alone.
        updater = ["/bin/sh", str(root / "scripts/whp-build/update-source.sh")]
        refreshed = subprocess.run(updater, cwd=root, env=env,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   text=True, check=True)
        assert "WHP DTC:" not in refreshed.stderr, refreshed.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == old_revision
        assert marker.read_text().strip() == legacy

        # Run the exact shell block from build.sh with the selected managed
        # Git represented by a tracing wrapper. No source download is needed
        # because the fixture already has the pinned commit in its object store.
        start_tag = "# WHP DTC post-host bootstrap reconciliation"
        block = build.split(start_tag, 1)[1].split("# Parse the LLVM switch", 1)[0]
        selected = root / "selected-git"
        trace = root / "git-commands.log"
        selected.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$WHP_DTC_GIT_TRACE"\n'
            'exec "$WHP_DTC_TEST_GIT" "$@"\n', encoding="utf-8"
        )
        selected.chmod(0o755)
        env["GIT"] = str(selected)
        env["WHP_DTC_TEST_GIT"] = shutil.which("git")
        env["WHP_DTC_GIT_TRACE"] = str(trace)
        env["SOURCE_DIR"] = str(root)
        env["WHP_DTC_FETCH_MISSING"] = "0"
        late = ["/bin/sh", "-c",
                '. "$WHP_SHARED_SHELL"\n' + block]
        env["WHP_SHARED_SHELL"] = str(SHARED_SHELL)

        # The reported regression: system libfdt must not run DTC
        # reconciliation or prevent the build from reaching configure.
        for provider in ("system", "disabled"):
            env["QEMU_FDT_MODE"] = provider
            env["WHP_DTC_FETCH_MISSING"] = "1"
            skipped = subprocess.run(late, cwd=root, env=env,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True,
                                     check=True)
            assert "reconciling pinned wrap" not in skipped.stderr
            assert git("rev-parse", "HEAD", cwd=checkout) == old_revision
            assert marker.read_text().strip() == legacy
            assert not trace.exists(), trace

        # QEMU configure has another reconciliation entry point. Reuse
        # its actual preflight block without requiring a full compiler/Meson
        # installation in this isolated Git fixture.
        start_comment = "  # The system and disabled libfdt providers"
        preflight = start_comment + configure.split(
            start_comment, 1
        )[1].split("  run_meson() {", 1)[0]
        env["source_path"] = str(root)
        env["python"] = sys.executable
        env["download"] = "enabled"
        run_preflight = ["/bin/sh", "-c",
                         'error_exit() { echo "$*" >&2; exit 2; }\n' + preflight]
        for provider in ("system", "disabled"):
            env["fdt_provider"] = provider
            skipped = subprocess.run(run_preflight, cwd=root, env=env,
                                     stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE,
                                     text=True, check=True)
            assert f"skipped (fdt={provider};" in skipped.stdout
            assert "pre-Meson Git reconciliation" not in skipped.stdout
            assert git("rev-parse", "HEAD", cwd=checkout) == old_revision
            assert marker.read_text().strip() == legacy

        # Internal libfdt must still reconcile and reject unsafe changes.
        env["QEMU_FDT_MODE"] = "internal"
        env["WHP_DTC_FETCH_MISSING"] = "0"
        first = subprocess.run(late, cwd=root, env=env,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               text=True, check=True)
        assert "reconciling pinned wrap after host Git/Python selection" in first.stderr
        assert "cat-file -e" in trace.read_text()
        assert git("rev-parse", "HEAD", cwd=checkout) == pin
        assert marker.read_text().strip() == expected
        assert marker.read_text().strip() != legacy

        # The direct configure path must also remain enabled for internal.
        env["fdt_provider"] = "internal"
        marker.write_text(legacy + "\n")
        checked = subprocess.run(run_preflight, cwd=root, env=env,
                                 stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, check=True)
        assert "pre-Meson Git reconciliation" in checked.stdout
        assert marker.read_text().strip() == expected

        marker_bytes = marker.read_bytes()
        second = subprocess.run(late, cwd=root, env=env,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, check=True)
        assert marker.read_bytes() == marker_bytes
        assert "reconciling pinned wrap" in second.stderr

        # A probe must not mutate even a stale marker.
        marker.write_text(legacy + "\n")
        env["WHP_PORTABLE_PROBE_ONLY"] = "1"
        subprocess.run(late, cwd=root, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert marker.read_text().strip() == legacy
        env.pop("WHP_PORTABLE_PROBE_ONLY")
        env["WHP_SHELL_PROBE_ONLY"] = "1"
        subprocess.run(late, cwd=root, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert marker.read_text().strip() == legacy
        env.pop("WHP_SHELL_PROBE_ONLY")

        # Source-update opt-out controls the automatic late repair.
        env["WHP_SOURCE_UPDATE"] = "0"
        subprocess.run(late, cwd=root, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert marker.read_text().strip() == legacy

        # The menu's explicit prefetch request remains authoritative even
        # with automatic source updates switched off.
        env["WHP_DTC_FETCH_MISSING"] = "1"
        subprocess.run(late, cwd=root, env=env, check=True,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert marker.read_text().strip() == expected

        # Parent refresh stays independent of DTC whether or not CI is active.
        marker.write_text(legacy + "\n")
        env["WHP_DTC_FETCH_MISSING"] = "0"
        env["WHP_SOURCE_UPDATE"] = "auto"
        for flag in ("false", "0", "true"):
            env["CI"] = flag
            proc = subprocess.run(updater, cwd=root, env=env,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                  text=True, check=True)
            assert marker.read_text().strip() == legacy
            assert "reconciling" not in proc.stderr
            if flag == "true":
                assert "skipped under CI" in proc.stderr
        env.pop("CI")


try:
    test_dtc_reconciles_after_host_tools()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"DTC post-host-tools integration: {exc}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("build source-update contract: verified")
