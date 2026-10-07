#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def load_helper():
    path = ROOT / "scripts/ensure-zlib.py"
    spec = importlib.util.spec_from_file_location("whp_ensure_zlib", path)
    if spec is None or spec.loader is None:
        raise SystemExit("error: could not load ensure-zlib.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    schema = (ROOT / "scripts/whp-config/menu-options.def").read_text(encoding="utf-8")
    host = (ROOT / "scripts/whp-build/host-libraries.sh").read_text(encoding="utf-8")
    helper_text = (ROOT / "scripts/ensure-zlib.py").read_text(encoding="utf-8")
    helper = load_helper()

    require(gitmodules, '[submodule "toolchains/zlib"]', "zlib submodule")
    require(gitmodules, "https://github.com/retrochristian5000/ZLIB.git", "WHP zlib source")
    require(config, "Option('BOOTSTRAP_ZLIB'", "zlib menu option")
    require(config, "'BOOTSTRAP_ZLIB',", "zlib tri-state shell policy")
    require(schema, "BOOTSTRAP_ZLIB|Host features|Bootstrap/use WHP zlib|choice|auto|auto,y,n|", "POSIX menu zlib option")
    require(host, "whp_prepare_bootstrap_zlib()", "bootstrap zlib phase")
    require(host, 'BOOTSTRAP_ZLIB=${BOOTSTRAP_ZLIB:-auto}', "zlib host-library switch")
    require(host, "scripts/ensure-zlib.py", "zlib bootstrap handoff")
    require(host, '--role bootstrap --cc "$CC_FOR_BUILD"', "Git zlib compiler boundary")
    require(host, "--role artifact", "artifact zlib role")
    require(host, "WHP_GIT_ZLIB_PREFIX", "Git-only zlib prefix")
    require(host, "WHP_ZLIB_PREFIX", "zlib downstream prefix")
    require(host, "ZLIB_ROOT", "CMake zlib root")
    require(helper_text, 'SUBMODULE_REL = pathlib.Path("toolchains/zlib")', "zlib gitlink path")
    require(helper_text, '("WHP_GIT_SEED", "GIT")', "seed Git source staging")
    require(helper_text, 'choices=("bootstrap", "artifact")', "zlib role CLI")
    require(helper_text, 'prefix_name = "git-zlib"', "Git zlib private prefix")
    require(helper_text, 'prefix_name = "zlib"', "artifact zlib private prefix")
    if '"git", "-C"' in helper_text:
        raise SystemExit("error: zlib source staging bypasses the selected seed Git")
    require(helper_text, '"--static"', "static-only zlib configure")
    require(helper_text, 'os.environ.get("WHP_INCREMENTAL_BUILD", "1")', "incremental default")
    require(helper_text, ".whp-zlib-workspace", "incremental workspace marker")
    require(helper_text, ".whp-zlib-bootstrap", "zlib cache marker")
    require(helper_text, '"libz.a"', "static archive verification")
    require(helper_text, '"zlib.pc"', "pkg-config verification")

    if helper.ZLIB_BOOTSTRAP_SCHEMA != "2":
        raise SystemExit("error: unexpected zlib bootstrap schema")
    if not helper.incremental_build_enabled():
        raise SystemExit("error: zlib incremental build must default on")
    if helper.zlib_cflags("", "", "") != ["-O3"]:
        raise SystemExit("error: portable zlib CFLAGS policy drifted")

    print("WHP zlib bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
