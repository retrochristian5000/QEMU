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
    'error: QEMU parent source update failed',
    'whp_select_seed_git()',
    'WHP_GIT_SEED=$("$SOURCE_DIR/seeds/git.sh" --print-seed) || return 1',
    'whp_select_seed_git || exit 1',
    '"$WHP_GIT_SEED" -C "$SOURCE_DIR" rev-parse HEAD',
    'scripts/whp-build/update-submodules.py',
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
seed_selection_index = build.find("    whp_select_seed_git || exit 1")
if not (0 <= seed_selection_index < refresh_index):
    errors.append("the validated Git seed must be bound before parent refresh")
host_tools_index = build.find('. "$SOURCE_DIR/scripts/whp-build/host-tools.sh"')
if not (refresh_index < host_tools_index and
        build.find('if [ "$WHP_GIT_SEED_SELECTED" != 1 ]; then',
                   refresh_index, host_tools_index) >= 0):
    errors.append("skipped source refresh must select Git once at host tools")

required_update = (
    'WHP_UPDATE_GIT=${WHP_GIT_SEED:-git}',
    'command -v "$WHP_UPDATE_GIT"',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" ls-remote "$remote" "$merge_ref"',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" fetch --no-tags --no-recurse-submodules',
    '"$remote" "$merge_ref:$upstream_ref"',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" merge --ff-only "$upstream_ref"',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" submodule sync --recursive',
    'upstream ref unchanged; object fetch skipped',
    'pinned submodules remain lazy',
    'DTC is reconciled by build.sh after the selected Python and Git bootstrap',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" diff --quiet --ignore-submodules=all --',
    '"$WHP_UPDATE_GIT" -C "$SOURCE_DIR" diff --cached --quiet --ignore-submodules=all --',
)
for needle in required_update:
    if needle not in update:
        errors.append(f"update-source.sh download-minimization contract missing: {needle}")

if 'git -C "$SOURCE_DIR"' in update:
    errors.append("early updater rediscovered ambient Git instead of its seed")

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

# Parent refresh and post-host-tool submodule alignment are separate phases.
submodule_index = build.find('scripts/whp-build/update-submodules.py')
if not (host_index < submodule_index < dtc_index):
    errors.append("initialized submodules must refresh after Git promotion and before DTC")
if not (ROOT / "scripts/whp-build/update-submodules.py").is_file():
    errors.append("missing initialized-submodule reconciliation helper")

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

# Only the explicitly requested internal provider is verified *after* the
# actual Meson setup; system/disabled keep their independent path. The check
# must never reset or reconfigure a successful incremental build.
post_meson = configure.split('  run_meson() {', 1)[-1].split(
    '  echo "$meson" > build.ninja.stamp', 1
)[0]
for required in (
    'if test "$fdt_provider" = internal &&',
    '--source "$source_path" --verify',
    'internal DTC Meson wrap verification failed',
):
    if required not in post_meson:
        errors.append(f"post-Meson DTC verification contract missing: {required}")

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


def test_parent_fast_forward_and_explicit_error():
    with tempfile.TemporaryDirectory(prefix='whp-source-parent-') as tmp:
        base = Path(tmp)
        upstream = base / 'upstream'
        upstream.mkdir()
        git('init', '-q', cwd=upstream)
        git('config', 'user.name', 'WHP Test', cwd=upstream)
        git('config', 'user.email', 'whp@example.invalid', cwd=upstream)
        (upstream / 'README').write_text('parent v1\n')
        git('add', 'README', cwd=upstream)
        git('commit', '-qm', 'parent v1', cwd=upstream)

        source = base / 'source'
        git('clone', '-q', str(upstream), str(source))
        script = source / 'scripts/whp-build/update-source.sh'
        script.parent.mkdir(parents=True)
        shutil.copy2(UPDATE, script)
        original = git('rev-parse', 'HEAD', cwd=source)
        (upstream / 'README').write_text('parent v2\n')
        git('add', 'README', cwd=upstream)
        git('commit', '-qm', 'parent v2', cwd=upstream)
        pinned = git('rev-parse', 'HEAD', cwd=upstream)

        env = os.environ.copy()
        env.pop('CI', None)
        env['WHP_SOURCE_UPDATE'] = 'auto'
        # Use a distinct selected Git wrapper. The parent updater must use it
        # for every Git command, not rediscover an unrelated PATH git.
        selected_git = base / 'selected-git'
        trace = base / 'selected-git.log'
        selected_git.write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$WHP_SELECTED_GIT_TRACE"\n'
            'exec "$WHP_TEST_REAL_GIT" "$@"\n', encoding='utf-8'
        )
        selected_git.chmod(0o755)
        env['WHP_GIT_SEED'] = str(selected_git)
        env['WHP_SELECTED_GIT_TRACE'] = str(trace)
        env['WHP_TEST_REAL_GIT'] = shutil.which('git')
        updater = ['/bin/sh', str(script)]
        first = subprocess.run(updater, cwd=source, env=env, text=True,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert first.returncode == 0, first.stderr
        traced = trace.read_text(encoding='utf-8')
        for command in ('rev-parse --is-inside-work-tree', 'ls-remote',
                        'fetch --no-tags', 'merge --ff-only'):
            assert command in traced, (command, traced)
        assert git('rev-parse', 'HEAD', cwd=source) == pinned
        assert original != pinned
        assert (source / 'README').read_text() == 'parent v2\n'

        unchanged = subprocess.run(updater, cwd=source, env=env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert unchanged.returncode == 0, unchanged.stderr
        assert 'upstream ref unchanged; object fetch skipped' in unchanged.stderr

        (upstream / 'README').write_text('parent v3\n')
        git('add', 'README', cwd=upstream)
        git('commit', '-qm', 'parent v3', cwd=upstream)
        (source / 'README').write_text('preserve local edit\n')
        env['WHP_SOURCE_UPDATE'] = '1'
        refused = subprocess.run(updater, cwd=source, env=env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert refused.returncode != 0
        assert 'tracked QEMU source changes' in refused.stderr
        assert git('rev-parse', 'HEAD', cwd=source) == pinned
        assert (source / 'README').read_text() == 'preserve local edit\n'

        env['WHP_SOURCE_UPDATE'] = '0'
        disabled = subprocess.run(updater, cwd=source, env=env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        assert disabled.returncode == 0
        assert git('rev-parse', 'HEAD', cwd=source) == pinned


def test_initialized_submodules_follow_parent_gitlinks():
    # A local pinned-submodule graph exercises both Git phases without any
    # public remote, destructive reset, or initialized-unused download.
    helper = ROOT / "scripts/whp-build/update-submodules.py"
    with tempfile.TemporaryDirectory(prefix="whp-source-submodules-") as tmp:
        base = Path(tmp)
        source = base / "parent"
        source.mkdir()
        modules = {}
        for name in ("a", "b"):
            module = base / name
            module.mkdir()
            git("init", "-q", cwd=module)
            git("config", "user.name", "WHP Test", cwd=module)
            git("config", "user.email", "whp@example.invalid", cwd=module)
            (module / "README").write_text(name + " v1\n")
            git("add", ".", cwd=module)
            git("commit", "-qm", name + " v1", cwd=module)
            modules[name] = module

        git("init", "-q", cwd=source)
        git("config", "user.name", "WHP Test", cwd=source)
        git("config", "user.email", "whp@example.invalid", cwd=source)
        for name, module in modules.items():
            git("-c", "protocol.file.allow=always", "submodule", "add",
                "-q", str(module), "modules/" + name, cwd=source)
        git("commit", "-qam", "initial parent gitlinks", cwd=source)
        parent_branch = git("symbolic-ref", "--short", "HEAD", cwd=source)

        clone = base / "clone"
        git("clone", "-q", str(source), str(clone))
        env = os.environ.copy()
        env.pop("CI", None)
        seed = shutil.which("git")
        selected = base / "selected-git"
        trace = base / "git-provider.log"
        selected.write_text(
            '#!/bin/sh\n'
            'printf "%s\\n" "$*" >> "$WHP_GIT_TRACE"\n'
            'exec "$WHP_GIT_SEED" "$@"\n',
            encoding="utf-8",
        )
        selected.chmod(0o755)
        env["GIT"] = str(selected)
        env["WHP_GIT_SEED"] = seed
        env["WHP_GIT_TRACE"] = str(trace)
        env["GIT_ALLOW_PROTOCOL"] = "file"
        env["WHP_SOURCE_UPDATE"] = "auto"
        subprocess.run(["git", "submodule", "update", "--init", "--",
                        "modules/a"], cwd=clone, env=env,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                       text=True, check=True)
        old = git("rev-parse", "HEAD", cwd=clone / "modules/a")
        assert not (clone / "modules/b/.git").exists()

        def pin_next_version(version):
            module = modules["a"]
            (module / "README").write_text("a v" + str(version) + "\n")
            git("add", ".", cwd=module)
            git("commit", "-qm", "a v" + str(version), cwd=module)
            new_pin = git("rev-parse", "HEAD", cwd=module)
            git("fetch", "--no-tags", str(module), new_pin,
                cwd=source / "modules/a")
            git("checkout", "--detach", new_pin,
                cwd=source / "modules/a")
            git("add", "modules/a", cwd=source)
            git("commit", "-qm", "pin a v" + str(version), cwd=source)
            git("-c", "fetch.recurseSubmodules=false", "pull", "--ff-only",
                str(source), parent_branch, cwd=clone)
            return new_pin

        def refresh():
            return subprocess.run(
                [sys.executable, str(helper), "--source", str(clone)],
                cwd=clone, env=env, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True,
            )

        current = pin_next_version(2)
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == old
        first = refresh()
        assert first.returncode == 0, first.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == current
        assert not (clone / "modules/b/.git").exists()
        assert "refreshed 1 of 1 initialized" in first.stderr
        assert "submodule update --init" in trace.read_text()
        again = refresh()
        assert again.returncode == 0, again.stderr
        assert "1 initialized and pinned" in again.stderr

        # An advancing parent gitlink cannot overwrite local submodule edits.
        new_pin = pin_next_version(3)
        (clone / "modules/a/README").write_text("local preservation\n")
        preserved = refresh()
        assert preserved.returncode == 0, preserved.stderr
        assert "preserving protected checkout" in preserved.stderr
        assert "local changes" in preserved.stderr
        env["WHP_SOURCE_UPDATE"] = "1"
        failure = refresh()
        assert failure.returncode != 0
        assert "local changes" in failure.stderr
        env["WHP_SOURCE_UPDATE"] = "auto"
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == current
        assert (clone / "modules/a/README").read_text() == "local preservation\n"
        assert new_pin != current

        # A divergent local commit must never be replaced by the parent pin.
        git("restore", "--", "README", cwd=clone / "modules/a")
        git("config", "user.name", "WHP Test", cwd=clone / "modules/a")
        git("config", "user.email", "whp@example.invalid",
            cwd=clone / "modules/a")
        (clone / "modules/a/README").write_text("local divergent commit\n")
        git("add", "README", cwd=clone / "modules/a")
        git("commit", "-qm", "local divergence", cwd=clone / "modules/a")
        divergent = git("rev-parse", "HEAD", cwd=clone / "modules/a")
        preserved_divergence = refresh()
        assert preserved_divergence.returncode == 0, preserved_divergence.stderr
        assert "preserving protected checkout" in preserved_divergence.stderr
        assert "divergent history" in preserved_divergence.stderr
        env["WHP_SOURCE_UPDATE"] = "1"
        refused = refresh()
        assert refused.returncode != 0
        assert "divergent history" in refused.stderr
        env["WHP_SOURCE_UPDATE"] = "auto"
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == divergent

        # A descendant of the parent pin is newer, even if it is detached.
        # Local source development must not be silently rolled back to v3.
        module = modules["a"]
        (module / "README").write_text("a v4\n")
        git("add", ".", cwd=module)
        git("commit", "-qm", "a v4 (not yet pinned)", cwd=module)
        newer = git("rev-parse", "HEAD", cwd=module)
        git("fetch", "--no-tags", str(module), newer,
            cwd=clone / "modules/a")
        git("checkout", "--detach", newer, cwd=clone / "modules/a")
        update_calls_before = trace.read_text().count("submodule update --init")
        ahead = refresh()
        assert ahead.returncode == 0, ahead.stderr
        assert "preserving newer checkout" in ahead.stderr
        assert "preserved 1 ahead of pins" in ahead.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        assert trace.read_text().count("submodule update --init") == update_calls_before
        assert not (clone / "modules/b/.git").exists()

        # Even uncommitted edits atop a newer descendant are left untouched.
        (clone / "modules/a/README").write_text("newer local edits\n")
        dirty_ahead = refresh()
        assert dirty_ahead.returncode == 0, dirty_ahead.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        assert (clone / "modules/a/README").read_text() == "newer local edits\n"

        # Optional initialized submodule with unavailable pin history must
        # not block auto bootstrap or overwrite a newer local checkout.
        missing_pin = pin_next_version(5)
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        missing_object = subprocess.run(
            ["git", "-C", str(clone / "modules/a"), "cat-file", "-e",
             missing_pin + "^{commit}"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
        )
        assert missing_object.returncode != 0, "fixture fetched pin prematurely"
        git("remote", "set-url", "origin", str(base / "missing-module-origin"),
            cwd=clone / "modules/a")
        env["WHP_SOURCE_UPDATE"] = "auto"
        unavailable = refresh()
        assert unavailable.returncode == 0, unavailable.stderr
        assert "pinned history fetch failed" in unavailable.stderr
        assert "preserving protected checkout" in unavailable.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        env["WHP_SOURCE_UPDATE"] = "1"
        strict = refresh()
        assert strict.returncode != 0, strict.stderr
        assert "cannot fetch pinned commit" in strict.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        env["WHP_SOURCE_UPDATE"] = "auto"

        # Source refresh can be opted out without touching the stale checkout.
        env["WHP_SOURCE_UPDATE"] = "0"
        skipped = refresh()
        assert skipped.returncode == 0, skipped.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == newer
        assert (clone / "modules/a/README").read_text() == "newer local edits\n"

def test_bootstrap_ancestry_guards():
    # Exercise the real pre-Python POSIX helper and the Python host-tool helper
    # with Git fixtures. Neither may move a newer or divergent checkout.
    with tempfile.TemporaryDirectory(prefix="whp-bootstrap-ancestry-") as tmp:
        base = Path(tmp)
        child = base / "child"
        parent = base / "parent"
        child.mkdir()
        parent.mkdir()
        for directory in (child, parent):
            git("init", "-q", cwd=directory)
            git("config", "user.name", "WHP Test", cwd=directory)
            git("config", "user.email", "whp@example.invalid", cwd=directory)
        (child / "README").write_text("v1\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "child v1", cwd=child)
        v1 = git("rev-parse", "HEAD", cwd=child)
        git("-c", "protocol.file.allow=always", "submodule", "add",
            "-q", str(child), "modules/a", cwd=parent)
        git("commit", "-qam", "initial parent pin", cwd=parent)
        branch = git("symbolic-ref", "--short", "HEAD", cwd=parent)
        clone = base / "clone"
        git("clone", "-q", str(parent), str(clone))
        env = os.environ.copy()
        env.pop("CI", None)
        env["GIT_ALLOW_PROTOCOL"] = "file"
        env["PYTHONPATH"] = str(ROOT / "scripts")
        subprocess.run(
            ["git", "submodule", "update", "--init", "--", "modules/a"],
            cwd=clone, env=env, check=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True,
        )

        shell_cmd = [
            "/bin/sh", "-c",
            '. "$1"; whp_git_submodule_prepare "$2" modules/a "${3:-git}"',
            "sh", str(SHARED_SHELL), str(clone),
        ]
        python_cmd = [
            sys.executable, "-c",
            "from bootstrap_env import reconcile_submodule; "
            "from pathlib import Path; "
            "reconcile_submodule(Path(__import__('sys').argv[1]), Path('modules/a'))",
            str(clone),
        ]

        def invoke(argv):
            return subprocess.run(
                argv, env=env, text=True, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )

        (child / "README").write_text("v2\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "child v2", cwd=child)
        v2 = git("rev-parse", "HEAD", cwd=child)
        git("fetch", "--no-tags", str(child), v2, cwd=parent / "modules/a")
        git("checkout", "--detach", v2, cwd=parent / "modules/a")
        git("add", "modules/a", cwd=parent)
        git("commit", "-qm", "pin child v2", cwd=parent)
        git("pull", "--ff-only", str(parent), branch, cwd=clone)

        # Git errors must not look like a clean, detached checkout.
        failed_probe_git = base / "failed-probe-git"
        failed_probe_git.write_text(
            '#!/bin/sh\n'
            'if [ "${3:-}" = "$WHP_TEST_FAILED_PROBE" ]; then\n'
            '    printf "Git test probe failed: %s\\n" "$3" >&2\n'
            '    exit 128\n'
            'fi\n'
            'exec "$WHP_TEST_REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        failed_probe_git.chmod(0o755)
        for probe in ("status", "symbolic-ref"):
            blocked = subprocess.run(
                [*shell_cmd, str(failed_probe_git)],
                env=dict(env, WHP_TEST_REAL_GIT=shutil.which("git"),
                         WHP_TEST_FAILED_PROBE=probe),
                capture_output=True, text=True,
            )
            assert blocked.returncode != 0, f"ignored Git {probe} failure"
            assert f"Git test probe failed: {probe}" in blocked.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v1

        # Python bootstrap can only move v1 -> v2 (a fast-forward).
        behind = invoke(python_cmd)
        assert behind.returncode == 0, behind.stderr
        assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v2

        (child / "README").write_text("v3\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "child v3", cwd=child)
        v3 = git("rev-parse", "HEAD", cwd=child)
        git("fetch", "--no-tags", str(child), v3, cwd=clone / "modules/a")
        git("checkout", "--detach", v3, cwd=clone / "modules/a")
        for invocation in (shell_cmd, python_cmd):
            ahead = invoke(invocation)
            assert ahead.returncode == 0, ahead.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v3

        # A Git command launched from a parent repository can inherit a
        # worktree override. It must not misidentify a valid newer child as
        # an unexpected Git worktree or redirect a write to the parent.
        contaminated = env.copy()
        contaminated["GIT_WORK_TREE"] = str(clone)
        contaminated["GIT_DIR"] = str(clone / ".git")
        contaminated["GIT_INDEX_FILE"] = str(clone / ".git/index")
        updater_cmd = [
            sys.executable,
            str(ROOT / "scripts/whp-build/update-submodules.py"),
            "--source", str(clone),
        ]
        contaminated["WHP_SOURCE_UPDATE"] = "1"
        for invocation in (shell_cmd, python_cmd, updater_cmd):
            result = subprocess.run(
                invocation, cwd=clone, env=contaminated,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            assert result.returncode == 0, result.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v3
            assert git("rev-parse", "HEAD:modules/a", cwd=clone) == v2

        # A newer checkout with uncommitted edits must not be checked out.
        (clone / "modules/a/README").write_text("local edits\n")
        ahead_dirty = invoke(shell_cmd)
        assert ahead_dirty.returncode == 0, ahead_dirty.stderr
        assert (clone / "modules/a/README").read_text() == "local edits\n"
        git("restore", "--", "README", cwd=clone / "modules/a")

        # An initialized submodule normally has a .git *file* referring to
        # metadata elsewhere. Its actual top-level working directory, not the
        # metadata location or literal path spelling, is the security boundary.
        assert (clone / "modules/a/.git").is_file()
        git_wrapper = base / "worktree-git"
        git_wrapper.write_text(
            '#!/bin/sh\n'
            'if [ "${3:-}" = rev-parse ] && '
            '[ "${4:-}" = --show-toplevel ]; then\n'
            '    printf "%s\\n" "$WHP_TEST_GIT_TOP"\n'
            '    exit 0\n'
            'fi\n'
            'exec "$WHP_TEST_REAL_GIT" "$@"\n',
            encoding="utf-8",
        )
        git_wrapper.chmod(0o755)
        alias = base / "same-worktree-alias"
        alias.symlink_to(clone / "modules/a", target_is_directory=True)
        report_env = env.copy()
        report_env["WHP_TEST_REAL_GIT"] = shutil.which("git")
        report_env["WHP_TEST_GIT_TOP"] = str(alias)
        shell_worktree_cmd = [
            "/bin/sh", "-c",
            '. "$1"; whp_git_submodule_prepare "$2" modules/a "$3"',
            "sh", str(SHARED_SHELL), str(clone), str(git_wrapper),
        ]
        python_worktree_cmd = [
            sys.executable, "-c",
            "from bootstrap_env import reconcile_submodule; "
            "from pathlib import Path; import sys; "
            "reconcile_submodule(Path(sys.argv[1]), Path('modules/a'), "
            "git=sys.argv[2])",
            str(clone), str(git_wrapper),
        ]
        for invocation in (shell_worktree_cmd, python_worktree_cmd):
            equivalent = subprocess.run(
                invocation, env=report_env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert equivalent.returncode == 0, equivalent.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v3

        # On case-insensitive APFS/HFS+, a case-only spelling of the same
        # directory is a valid worktree. Linux case-sensitive filesystems
        # skip this scenario because the alternate path does not exist.
        case_alias = clone / "MODULES" / "A"
        if case_alias.exists() and case_alias.samefile(clone / "modules/a"):
            report_env["WHP_TEST_GIT_TOP"] = str(case_alias)
            for invocation in (shell_worktree_cmd, python_worktree_cmd):
                equivalent_case = subprocess.run(
                    invocation, env=report_env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                assert equivalent_case.returncode == 0, equivalent_case.stderr
                assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v3

        # The same newer commit must not excuse *another* worktree root.
        report_env["WHP_TEST_GIT_TOP"] = str(child)
        for invocation in (shell_worktree_cmd, python_worktree_cmd):
            foreign = subprocess.run(
                invocation, env=report_env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert foreign.returncode != 0, foreign.stderr
            assert "unexpected" in foreign.stderr, foreign.stderr
            assert "Git:" in foreign.stderr, foreign.stderr
            assert "expected:" in foreign.stderr, foreign.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v3

        # A locally committed branch from v1 is divergent from parent pin v2.
        git("checkout", "--detach", v1, cwd=clone / "modules/a")
        git("config", "user.name", "WHP Test", cwd=clone / "modules/a")
        git("config", "user.email", "whp@example.invalid",
            cwd=clone / "modules/a")
        (clone / "modules/a/README").write_text("independent local history\n")
        git("add", "README", cwd=clone / "modules/a")
        git("commit", "-qm", "local diverged", cwd=clone / "modules/a")
        local = git("rev-parse", "HEAD", cwd=clone / "modules/a")
        for invocation in (shell_cmd, python_cmd):
            diverged = invoke(invocation)
            assert diverged.returncode != 0, diverged.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == local

        # A dirty, behind checkout is likewise preserved.
        git("checkout", "--detach", v1, cwd=clone / "modules/a")
        (clone / "modules/a/README").write_text("dirty old source\n")
        for invocation in (shell_cmd, python_cmd):
            dirty = invoke(invocation)
            assert dirty.returncode != 0, dirty.stderr
            assert git("rev-parse", "HEAD", cwd=clone / "modules/a") == v1
            assert (clone / "modules/a/README").read_text() == "dirty old source\n"



def test_bootstrap_shallow_newer_descendants():
    # Reproduce a real builder with pin X initialized at depth one, followed
    # by a fresh GitHub checkout at newer Y with a disconnected shallow edge.
    # Both the public pre-Python shell and managed Python host-tool reconciler
    # must fetch only history, preserve Y and never silently check out X.
    with tempfile.TemporaryDirectory(prefix="whp-shallow-python-") as tmp:
        base = Path(tmp)
        upstream = base / "upstream"
        upstream.mkdir()
        git("init", "-q", cwd=upstream)
        git("config", "user.name", "WHP Test", cwd=upstream)
        git("config", "user.email", "whp@example.invalid", cwd=upstream)
        (upstream / "README").write_text("Python fork X\\n")
        git("add", ".", cwd=upstream)
        git("commit", "-qm", "Python pin X", cwd=upstream)
        pin = git("rev-parse", "HEAD", cwd=upstream)

        parent = base / "parent"
        parent.mkdir()
        git("init", "-q", cwd=parent)
        git("config", "user.name", "WHP Test", cwd=parent)
        git("config", "user.email", "whp@example.invalid", cwd=parent)
        path = "toolchains/python-runtime"
        git("-c", "protocol.file.allow=always", "submodule", "add",
            "-q", upstream.as_uri(), path, cwd=parent)
        git("commit", "-qam", "pin Python X", cwd=parent)

        (upstream / "README").write_text("Python fork Y\\n")
        git("add", ".", cwd=upstream)
        git("commit", "-qm", "Python newer Y", cwd=upstream)
        newer = git("rev-parse", "HEAD", cwd=upstream)
        env = os.environ.copy()
        env["GIT_ALLOW_PROTOCOL"] = "file"
        env["PYTHONPATH"] = str(ROOT / "scripts")

        for lane in ("shell", "python", "updater", "legacy"):
            clone = base / lane
            git("clone", "-q", str(parent), str(clone))
            checkout = clone / path
            subprocess.run(
                ["git", "submodule", "update", "--init", "--depth", "1",
                 "--", path],
                cwd=clone, env=env, check=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            )
            assert git("rev-parse", "HEAD", cwd=checkout) == pin
            git("fetch", "--depth=1", "origin", newer, cwd=checkout)
            git("checkout", "--detach", newer, cwd=checkout)
            assert git("rev-parse", "--is-shallow-repository",
                       cwd=checkout) == "true"
            hidden = subprocess.run(
                ["git", "-C", str(checkout), "merge-base",
                 "--is-ancestor", pin, newer],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                text=True, check=False,
            )
            assert hidden.returncode == 1, hidden.stderr

            if lane == "shell":
                base_cmd = [
                    "/bin/sh", "-c",
                    '. "$1"; whp_git_submodule_prepare "$2" '
                    'toolchains/python-runtime "$3" "$4"',
                    "sh", str(SHARED_SHELL), str(clone), "git",
                ]
                offline = subprocess.run(
                    [*base_cmd, "offline"], env=env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                assert offline.returncode != 0, offline.stderr
                assert git("rev-parse", "HEAD", cwd=checkout) == newer
                command = [*base_cmd, "online"]
            elif lane == "python":
                command = [
                    sys.executable, "-c",
                    "from pathlib import Path; "
                    "from bootstrap_env import reconcile_submodule; "
                    "import sys; "
                    "reconcile_submodule(Path(sys.argv[1]), "
                    "Path('toolchains/python-runtime'))",
                    str(clone),
                ]
            elif lane == "updater":
                env["WHP_SOURCE_UPDATE"] = "1"  # CI skips auto mode.
                command = [
                    sys.executable,
                    str(ROOT / "scripts/whp-build/update-submodules.py"),
                    "--source", str(clone),
                ]
            else:
                scripts = clone / "scripts"
                shared = scripts / "whp-build"
                shared.mkdir(parents=True)
                shutil.copy2(ROOT / "scripts/git-submodule.sh",
                             scripts / "git-submodule.sh")
                shutil.copy2(SHARED_SHELL, shared / "shell-functions.sh")
                command = ["/bin/sh", "scripts/git-submodule.sh",
                           "update", path]
                validation = subprocess.run(
                    ["/bin/sh", "scripts/git-submodule.sh",
                     "validate", path],
                    cwd=clone, env=env, text=True,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                assert validation.returncode != 0
                assert not (clone / ".git-submodule-status").exists()

            result = subprocess.run(
                command, cwd=clone, env=env, text=True,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert result.returncode == 0, result.stderr
            assert git("rev-parse", "HEAD", cwd=checkout) == newer
            if lane == "updater":
                assert "preserving newer checkout" in result.stderr, result.stderr
            else:
                assert "newer shallow" in result.stderr, result.stderr
            proven = subprocess.run(
                ["git", "-C", str(checkout), "merge-base",
                 "--is-ancestor", pin, newer],
                check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            assert proven.returncode == 0, result.stderr
            assert (checkout / "README").read_text() == "Python fork Y\\n"


def test_explicit_remote_submodule_refresh():
    # Single-path remote updates are opt-in; parent gitlinks and other
    # submodule working trees must remain pinned/lazy.
    helper = ROOT / "scripts/whp-build/update-submodules.py"
    with tempfile.TemporaryDirectory(prefix="whp-submodule-remote-") as tmp:
        base = Path(tmp)
        child, parent, clone = (base / name for name in ("child", "parent", "clone"))
        child.mkdir()
        parent.mkdir()
        for directory in (child, parent):
            git("init", "-q", cwd=directory)
            git("config", "user.name", "WHP Test", cwd=directory)
            git("config", "user.email", "whp@example.invalid", cwd=directory)
        (child / "README").write_text("v1\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "v1", cwd=child)
        old = git("rev-parse", "HEAD", cwd=child)
        child_branch = git("symbolic-ref", "--short", "HEAD", cwd=child)
        git("-c", "protocol.file.allow=always", "submodule", "add", "-q",
            str(child), "modules/a", cwd=parent)
        git("config", "-f", ".gitmodules", "submodule.modules/a.branch",
            child_branch, cwd=parent)
        git("add", ".gitmodules", cwd=parent)
        git("commit", "-qam", "pin v1", cwd=parent)
        git("clone", "-q", str(parent), str(clone))
        env = os.environ.copy()
        env.pop("CI", None)
        env["GIT_ALLOW_PROTOCOL"] = "file"
        env["WHP_SOURCE_UPDATE"] = "1"
        subprocess.run(
            ["git", "submodule", "update", "--init", "--", "modules/a"],
            cwd=clone, env=env, check=True, capture_output=True, text=True,
        )
        checkout = clone / "modules/a"

        def invoke(*args):
            return subprocess.run(
                [sys.executable, str(helper), "--source", str(clone), *args],
                cwd=clone, env=env, capture_output=True, text=True,
            )

        (child / "README").write_text("v2\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "v2", cwd=child)
        remote_tip = git("rev-parse", "HEAD", cwd=child)
        # A normal pinned refresh must never follow the tracking branch.
        pinned = invoke()
        assert pinned.returncode == 0, pinned.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == old
        assert invoke("--remote").returncode != 0
        assert invoke("modules/a").returncode != 0
        assert invoke("--remote", "modules/unknown").returncode != 0

        updated = invoke("--remote", "modules/a")
        assert updated.returncode == 0, updated.stderr
        assert "parent gitlink unchanged" in updated.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == remote_tip
        assert git("rev-parse", "HEAD:modules/a", cwd=clone) == old
        assert old in git("ls-files", "--stage", "modules/a", cwd=clone)
        assert invoke("--remote", "modules/a").returncode == 0

        # A staged newer descendant must not block a no-op remote refresh.
        git("add", "modules/a", cwd=clone)
        staged = invoke("--remote", "modules/a")
        assert staged.returncode == 0, staged.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == remote_tip
        assert remote_tip in git("ls-files", "--stage", "modules/a", cwd=clone)

        (child / "README").write_text("v3\n")
        git("add", ".", cwd=child)
        git("commit", "-qm", "v3", cwd=child)
        # Moving the checkout remains forbidden while its gitlink is staged.
        blocked = invoke("--remote", "modules/a")
        assert blocked.returncode != 0
        assert "staged gitlink" in blocked.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == remote_tip
        assert remote_tip in git("ls-files", "--stage", "modules/a", cwd=clone)
        git("reset", "-q", "--", "modules/a", cwd=clone)
        (checkout / "README").write_text("local edits\n")
        dirty = invoke("--remote", "modules/a")
        assert dirty.returncode != 0
        assert "local edits" in dirty.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == remote_tip
        git("restore", "--", "README", cwd=checkout)
        git("checkout", "-qb", "development", cwd=checkout)
        branch = invoke("--remote", "modules/a")
        assert branch.returncode != 0
        assert "attached development branch" in branch.stderr
        git("checkout", "-q", "--detach", remote_tip, cwd=checkout)
        advanced = invoke("--remote", "modules/a")
        assert advanced.returncode == 0, advanced.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == git(
            "rev-parse", "HEAD", cwd=child
        )

        # A local descendant must be kept when the remote has not caught up.
        git("config", "user.name", "WHP Test", cwd=checkout)
        git("config", "user.email", "whp@example.invalid", cwd=checkout)
        (checkout / "README").write_text("local newer\n")
        git("add", ".", cwd=checkout)
        git("commit", "-qm", "local newer", cwd=checkout)
        newer = git("rev-parse", "HEAD", cwd=checkout)
        preserved = invoke("--remote", "modules/a")
        assert preserved.returncode == 0, preserved.stderr
        assert "preserving newer local" in preserved.stderr
        assert git("rev-parse", "HEAD", cwd=checkout) == newer
        assert git("rev-parse", "HEAD:modules/a", cwd=clone) == old

        # An attached branch already ahead of the verified remote is usable
        # without changing its HEAD or the recorded parent gitlink.
        git("checkout", "-qb", "newer-development", cwd=checkout)
        attached_newer = invoke("--remote", "modules/a")
        assert attached_newer.returncode == 0, attached_newer.stderr
        assert "preserving newer local" in attached_newer.stderr
        assert git("symbolic-ref", "--short", "HEAD",
                   cwd=checkout) == "newer-development"
        assert git("rev-parse", "HEAD", cwd=checkout) == newer
        assert git("rev-parse", "HEAD:modules/a", cwd=clone) == old


try:
    test_explicit_remote_submodule_refresh()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"explicit remote submodule update integration: {exc}")

try:
    test_dtc_reconciles_after_host_tools()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"DTC post-host-tools integration: {exc}")

try:
    test_initialized_submodules_follow_parent_gitlinks()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"initialized submodule refresh integration: {exc}")

try:
    test_bootstrap_ancestry_guards()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"bootstrap ancestry guard integration: {exc}")

try:
    test_bootstrap_shallow_newer_descendants()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"shallow Python and host bootstrap reconciliation: {exc}")

try:
    test_parent_fast_forward_and_explicit_error()
except (AssertionError, OSError, subprocess.CalledProcessError) as exc:
    errors.append(f"parent source fast-forward integration: {exc}")

if errors:
    for error in errors:
        print(f"FAIL: {error}", file=sys.stderr)
    raise SystemExit(1)

print("build source-update contract: verified")
