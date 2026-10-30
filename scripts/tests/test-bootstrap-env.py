#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Regression test for target-environment bleed and bootstrap cache inputs."""

from __future__ import annotations

import importlib.util
import pathlib
import stat
import tempfile
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "whp_bootstrap_env", ROOT / "scripts/bootstrap_env.py"
)
assert spec is not None and spec.loader is not None
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)

poison = {
    "PATH": "/usr/bin:/bin", "SDKROOT": "/selected/MacOSX.sdk",
    "DEVELOPER_DIR": "/selected/Developer", "CC_FOR_BUILD": "/selected/clang",
    "WHP_GREP_SEED": "/usr/bin/grep", "WHP_SED_SEED": "/usr/bin/sed",
    "CC": "/target/cc", "CFLAGS": "-fdeliberately-invalid",
    "LDFLAGS": "-Wl,--bad", "MAKEFLAGS": "--bad",
    "MAKEOVERRIDES": "CC=/target/cc", "CONFIG_SITE": "/target/site",
    "ACLOCAL_PATH": "/target/m4", "PKG_CONFIG_SYSROOT_DIR": "/target/sysroot",
    "LD_LIBRARY_PATH": "/target/lib", "DYLD_INSERT_LIBRARIES": "/target/lib",
    "ASAN_OPTIONS": "detect_leaks=0", "ac_cv_func_malloc_0_nonnull": "yes",
    "gl_cv_func_test": "poison", "make_cv_jobserver": "bad",
    "lt_cv_sys_max_cmd_len": "1",
}
env = module.clean_host_environment(poison)
for key in ("PATH", "SDKROOT", "DEVELOPER_DIR", "CC_FOR_BUILD",
            "WHP_GREP_SEED", "WHP_SED_SEED"):
    assert env[key] == poison[key], key
for key in poison:
    if key not in ("PATH", "SDKROOT", "DEVELOPER_DIR", "CC_FOR_BUILD",
                   "WHP_GREP_SEED", "WHP_SED_SEED"):
        assert key not in env, key
assert poison["CC"] == "/target/cc"

with tempfile.TemporaryDirectory(prefix="whp-bootstrap-env-") as td:
    base = pathlib.Path(td)
    cc = base / "native-cc"
    cc.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    cc.chmod(cc.stat().st_mode | stat.S_IXUSR)
    adapter = base / "cc.sh"
    adapter.write_text(
        "#!/bin/sh\nprintf '%s\\n' '" + str(cc) + "'\n",
        encoding="utf-8",
    )
    adapter.chmod(adapter.stat().st_mode | stat.S_IXUSR)
    assert module.select_native_cc(base) == str(cc)
    adapter.write_text("#!/bin/sh\nprintf 'invalid\\n'\n", encoding="utf-8")
    try:
        module.select_native_cc(base)
    except RuntimeError as exc:
        assert "valid native bootstrap compiler" in str(exc)
    else:
        raise AssertionError("accepted invalid CC seed")

# A Darwin bootstrap must validate SDKROOT through the same selected
# Xcode/CLT helper; never assume cc.sh's test SDK is inherited by configure.
with tempfile.TemporaryDirectory(prefix="whp-bootstrap-sdk-") as td:
    base = pathlib.Path(td)
    helper = base / "scripts/whp-build/macos-developer-tools.sh"
    helper.parent.mkdir(parents=True)
    sdk = base / "MacOSX.sdk"
    sdk.mkdir()
    helper.write_text(
        'whp_apple_check_sdkroot() { [ -d "$1" ]; }\n'
        'whp_apple_find_sdk() { printf "%s\\n" "$TEST_NATIVE_SDK"; }\n',
        encoding="utf-8",
    )
    with mock.patch.object(module.platform, "system", return_value="Darwin"):
        with mock.patch.dict(
            module.os.environ,
            {"SDKROOT": str(sdk), "TEST_NATIVE_SDK": str(sdk)},
        ):
            assert module.select_native_sdk(base) == str(sdk)
            module.os.environ["SDKROOT"] = ""
            assert module.select_native_sdk(base) == str(sdk)
            module.os.environ["SDKROOT"] = str(base / "missing")
            try:
                module.select_native_sdk(base)
            except RuntimeError as exc:
                assert "selected macOS SDK" in str(exc)
            else:
                raise AssertionError("accepted nonexistent Darwin SDK")
    with mock.patch.object(module.platform, "system", return_value="Linux"):
        assert module.select_native_sdk(base) == ""

for filename in ("ensure-automake.py", "ensure-autoconf.py", "ensure-git.py"):
    source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
    assert "clean_host_environment(os.environ)" in source, filename
    assert 'env["CC"] = cc' in source, filename
    assert 'env["MAKE"] = make' in source, filename
for filename in ("ensure-automake.py", "ensure-autoconf.py"):
    source = (ROOT / "scripts" / filename).read_text(encoding="utf-8")
    assert "cc = select_native_cc(ROOT)" in source, filename
    assert "sdkroot = select_native_sdk(ROOT)" in source, filename
    assert 'os.environ["SDKROOT"] = sdkroot' in source, filename
    assert 'f"CONFIG_SHELL={config_shell}' in source, filename
    assert 'f"CC_FOR_BUILD={cc}' in source, filename
print("WHP native bootstrap environment and cache provenance: verified")
