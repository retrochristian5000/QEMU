#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import configparser
from contextlib import ExitStack
import importlib.util
import pathlib
import sys
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")



def verify_git_cache_recovery() -> None:
    """Exercise cache-before-build and failed-install rollback without network."""
    spec = importlib.util.spec_from_file_location(
        "whp_git_bootstrap_test", ROOT / "scripts/ensure-git.py"
    )
    assert spec is not None and spec.loader is not None
    if str(ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(ROOT / "scripts"))
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)

    with tempfile.TemporaryDirectory(prefix="whp-git-cache-") as temp:
        build = pathlib.Path(temp)
        prefix = build / "deps/git"
        (prefix / "bin").mkdir(parents=True)
        binary = prefix / "bin/git"
        binary.write_text("previous Git\n", encoding="utf-8")
        marker = prefix / ".whp-git-bootstrap"
        marker.write_text("core-cache\n", encoding="utf-8")

        overrides = {
            "seed_git": mock.Mock(return_value="seed"),
            "ensure_source": mock.Mock(return_value=("revision", "sha1")),
            "select_macos_sdkroot": mock.Mock(return_value=""),
            "select_cc": mock.Mock(return_value="cc"),
            "select_bootstrap_cflags": mock.Mock(return_value=""),
            "select_bootstrap_ldflags": mock.Mock(return_value=""),
            "select_gnu_make": mock.Mock(return_value="make"),
            "curl_prefix": mock.Mock(return_value=""),
            "iconv_prefix": mock.Mock(return_value=""),
            "zlib_prefix": mock.Mock(return_value=("", "")),
            "marker_text": mock.Mock(
                side_effect=lambda *args: args[5] + "-cache\n"
            ),
            "git_usable": mock.Mock(return_value=True),
            "smoke_local": mock.Mock(return_value=True),
            "has_https_transport": mock.Mock(return_value=False),
            "build_profile": mock.Mock(
                side_effect=AssertionError("cache hit must not rebuild Git")
            ),
        }
        with ExitStack() as patches:
            for name, replacement in overrides.items():
                patches.enter_context(mock.patch.object(helper, name, replacement))
            assert helper.bootstrap(build, "auto") == prefix
            overrides["build_profile"].assert_not_called()

        def install_fails(argv, **kwargs):
            if "install" in argv:
                raise RuntimeError("simulated Git install failure")

        with (
            mock.patch.object(helper, "copy_source"),
            mock.patch.object(helper, "validate_build_compiler"),
            mock.patch.object(helper, "run_logged", side_effect=install_fails),
            mock.patch.dict(helper.os.environ, {"JOBS": "1"}),
        ):
            try:
                helper.build_profile(
                    "seed", "revision", "sha1", "cc", "make", build,
                    "core", "", "", "", "", "", "", "replacement-cache\n",
                )
            except RuntimeError as exc:
                assert "simulated Git install failure" in str(exc)
            else:
                raise AssertionError("Git install failure was not reported")

        assert binary.read_text(encoding="utf-8") == "previous Git\n"
        assert marker.read_text(encoding="utf-8") == "core-cache\n"
        assert not (prefix.parent / ".whp-git-previous").exists()

        # An unusable cache marker is also a failed install. Restore the old
        # Git executable and its provenance, not just the executable itself.
        def install_replacement(argv, **kwargs):
            if "install" in argv:
                (prefix / "bin").mkdir(parents=True, exist_ok=True)
                (prefix / "bin/git").write_text(
                    "replacement Git\n", encoding="utf-8"
                )

        original_write = pathlib.Path.write_text

        def reject_new_marker(path, content, **kwargs):
            if path == marker:
                raise OSError("simulated cache marker failure")
            return original_write(path, content, **kwargs)

        with (
            mock.patch.object(helper, "copy_source"),
            mock.patch.object(helper, "validate_build_compiler"),
            mock.patch.object(helper, "run_logged", side_effect=install_replacement),
            mock.patch.object(helper, "git_usable", return_value=True),
            mock.patch.object(helper, "smoke_local", return_value=True),
            mock.patch.object(helper.pathlib.Path, "write_text", autospec=True,
                              side_effect=reject_new_marker),
        ):
            try:
                helper.build_profile(
                    "seed", "revision", "sha1", "cc", "make", build,
                    "core", "", "", "", "", "", "", "replacement-cache\n",
                )
            except OSError as exc:
                assert "simulated cache marker failure" in str(exc)
            else:
                raise AssertionError("Git marker write failure was not reported")

        assert binary.read_text(encoding="utf-8") == "previous Git\n"
        assert marker.read_text(encoding="utf-8") == "core-cache\n"
        assert not (prefix.parent / ".whp-git-previous").exists()

        # A concurrent bootstrap must not alter the active source or Git cache.
        with helper.git_bootstrap_lock(build):
            try:
                with helper.git_bootstrap_lock(build):
                    raise AssertionError("nested Git bootstrap acquired the lock")
            except RuntimeError as exc:
                assert "another WHP Git bootstrap" in str(exc)
        with helper.git_bootstrap_lock(build):
            pass

def main() -> int:
    parser = configparser.ConfigParser()
    parser.read(ROOT / ".gitmodules", encoding="utf-8")
    section = 'submodule "toolchains/git"'
    if section not in parser:
        raise SystemExit("error: WHP Git fork is not registered")
    if parser[section].get("url") != "https://github.com/retrochristian5000/git-tools.git":
        raise SystemExit("error: toolchains/git does not point at the WHP Git fork")

    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    require(host_tools, "BOOTSTRAP_GIT=", "Git bootstrap policy")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    updater = (ROOT / "scripts/whp-build/update-source.sh").read_text(
        encoding="utf-8"
    )
    adapter = (ROOT / "git.sh").read_text(encoding="utf-8")
    require(build, 'WHP_GIT_SEED=$("$SOURCE_DIR/git.sh" --print-seed)',
            "early Git seed boundary")
    require(build, 'whp_select_seed_git || exit 1',
            "Git selection before updater")
    require(build, 'printf \'QEMU seed git:', "single seed diagnostic")
    require(updater, 'WHP_UPDATE_GIT=${WHP_GIT_SEED:-git}',
            "parent updater selects the same Git seed")
    require(host_tools, 'WHP_GIT_SEED_SELECTED:-0',
            "managed stages reuse selected Git seed")
    if '"$SOURCE_DIR/git.sh" --print-seed' in host_tools:
        raise SystemExit("error: Git seed must not be reselected after source update")
    if "| grep -q '^git version '" in adapter:
        raise SystemExit("error: early Git seed still depends on late grep")
    require(host_tools, "whp_prepare_bootstrap_zlib", "pre-Git zlib phase")
    require(host_tools, "git-remote-https", "HTTPS promotion guard")
    require(host_tools, "WHP_GIT_LOCAL", "local Git fallback")
    require(host_tools, 'GIT="$WHP_GIT_SEED"',
            "explicit validated-seed fallback for DTC")
    require(host_tools, 'if [ -z "${GIT:-}" ]; then',
            "caller Git override preservation")


    helper = (ROOT / "scripts/ensure-git.py").read_text(encoding="utf-8")
    require(helper, 'SUBMODULE_REL = pathlib.Path("toolchains/git")', "Git pin")
    require(helper, 'SHA1_REL = pathlib.Path("sha1collisiondetection")', "SHA-1 pin")
    require(helper, '"NO_CURL=YesPlease"', "local transport boundary")
    if '"NO_ICONV=YesPlease"' in helper:
        raise SystemExit(
            "error: managed Git must not combine Darwin PRECOMPOSE_UNICODE with NO_ICONV"
        )
    require(helper, "iconv_prefix", "Darwin iconv dependency")
    require(helper, '"DC_SHA1_SUBMODULE=YesPlease"', "collision-detection source")
    require(helper, 'os.environ.get("WHP_GIT_ZLIB_PREFIX", "")', "managed zlib input")
    require(helper, 'variables.append(f"ZLIB_PATH={zlib_dir}")', "Git zlib link path")
    require(helper, 'f"ZLIB_ID={zlib_id}\\n"', "Git zlib cache identity")
    require(helper, "has_https_transport", "managed transport probe")
    require(helper, 'GIT_BOOTSTRAP_SCHEMA = "5"', "Git native environment cache invalidation")
    require(helper, 'sdkroot = select_macos_sdkroot()', "Git native SDK resolution")
    require(helper, 'os.environ["SDKROOT"] = sdkroot', "CC seed SDK handoff")
    require(helper, 'env["SDKROOT"] = sdkroot', "Git Make SDK handoff")
    require(helper, "whp_apple_check_sdkroot", "selected Xcode/CLT SDK guard")
    require(helper, "validate_build_compiler(cc, env, work)",
            "Git C compiler header, link and execution preflight")
    require(helper, '"#include <unistd.h>\\n"', "missing POSIX header regression")
    require(helper, 'f"SDKROOT={sdkroot}', "SDK in Git cache identity")

    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")
    require(ledger, "Git bootstrap boundary", "Git circularity section")
    require(ledger, "seed Git", "seed Git root")
    require(ledger, "Git -> checkout Git", "self-cycle warning")

    prepare = (ROOT / "scripts/whp-build/prepare-sources.bash").read_text(
        encoding="utf-8"
    )
    require(
        prepare,
        'whp_git_submodule_prepare "$SOURCE_DIR" "$whp_module" "${GIT:-git}"',
        "promoted Git for submodule ancestry",
    )
    if prepare.count('"${GIT:-git}" -C "$SOURCE_DIR" submodule sync --') != 3:
        raise SystemExit("error: firmware source sync bypasses promoted Git")
    verify_git_cache_recovery()
    print("WHP Git dependency policy: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
