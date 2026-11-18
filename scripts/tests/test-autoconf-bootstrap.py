#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
from pathlib import Path
import tempfile

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")


def check_m4_runtime_guard() -> None:
    """Reject an M4 impostor that prints a valid banner but cannot expand macros."""
    helper_path = ROOT / "scripts/ensure-autoconf.py"
    spec = importlib.util.spec_from_file_location("whp_ensure_autoconf", helper_path)
    if spec is None or spec.loader is None:
        raise SystemExit("error: cannot import the Autoconf bootstrap helper")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    with tempfile.TemporaryDirectory(prefix="whp-m4-regression-") as directory:
        fake = Path(directory) / "fake-m4"
        fake.write_text(
            '#!/bin/sh\n'
            'if [ "$1" = --gnu ] && [ "$2" = --version ]; then\n'
            "  printf '%s\\n' 'm4 (GNU M4) 99.99'\n"
            '  exit 0\n'
            'fi\n'
            "printf '%s\\n' 'not-expanded'\n",
            encoding="utf-8",
        )
        fake.chmod(0o755)
        try:
            module.gnu_m4_version(str(fake))
        except RuntimeError as exc:
            require(str(exc), "GNU M4 macro expansion failed", "M4 runtime guard")
        else:
            raise SystemExit("error: accepted M4 with a forged version banner")


def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-autoconf.py").read_text(encoding="utf-8")
    host_tools = (ROOT / "scripts/whp-build/host-tools.sh").read_text(
        encoding="utf-8"
    )
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    ledger = (ROOT / "docs/devel/whp-dependency-ledger.rst").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/autoconf"]', "Autoconf submodule")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/autoconf.git",
        "WHP Autoconf fork URL",
    )
    require(helper, 'SUBMODULE_REL = pathlib.Path("toolchains/autoconf")', "pinned source")
    # Python already resolves the bootstrap work and build directories.
    # The pinned Autoconf bootstrap invokes mktemp, not standalone realpath.
    # A missing realpath executable must not reject otherwise valid hosts.
    if 'tool("realpath")' in helper:
        raise SystemExit("error: unused realpath CLI dependency reintroduced")
    require(helper, 'tool("mktemp")', "Autoconf source bootstrap temporary directory")
    require(helper, 'pathlib.Path(args.build_dir).expanduser().resolve()',
            "native Python path normalization")
    require(helper, 'AUTOCONF_BOOTSTRAP_SCHEMA = "6"', "native environment schema")
    require(helper, '[path, "--gnu", "--version"]', "GNU M4 capability probe")
    require(helper, '[path, "--gnu", "--fatal-warnings"]', "GNU M4 runtime probe")
    require(helper, "GNU M4 1.4.16 or newer", "GNU M4 bootstrap floor")
    require(helper, 'f"M4_PATH={m4}\\n"', "M4 path marker")
    require(helper, 'jobs = parallel_jobs(os.environ.get("JOBS"))',
            "pre-install job validation")
    require(helper, 'for name in REQUIRED_BINARIES:',
            "complete installed suite validation")
    require(helper, 'folder.rglob("*")',
            "source archive macro and library fingerprint")
    require(helper, 'f"M4_VERSION={gnu_m4_version(m4)}\\n"', "M4 version marker")
    require(helper, 'f"AWK={awk}\\n"', "AWK cache handoff")
    require(helper, 'f"GREP={grep}\\n"', "grep cache handoff")
    require(helper, 'env["AWK"] = awk', "selected AWK command")
    require(helper, 'env["GREP"] = grep', "selected grep command")
    require(
        helper,
        '("AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF", "M4")',
        "installed-runtime M4 isolation",
    )
    seed = (ROOT / "seeds/gnum4.sh").read_text(encoding="utf-8")
    generic = (ROOT / "seeds/m4.sh").read_text(encoding="utf-8")
    require(helper, 'ROOT / "seeds" / "gnum4.sh"', "dedicated GNU M4 seed")
    require(generic, "WHP generic M4 seed:", "generic M4 identity")
    require(seed, "WHP_GNUM4_SEED", "GNU M4 override isolation")
    require(helper, '["/bin/sh", str(adapter), "--print-seed"]',
            "GNU M4 seed selection call")
    brew_seed = (ROOT / "seeds/brew.sh").read_text(encoding="utf-8")
    require(seed, '--formula-bin m4 m4',
            "selected Homebrew keg-only M4 discovery")
    require(seed, 'macports|system) ;;',
            "non-Homebrew provider isolation")
    require(brew_seed, '"$selected_brew" --prefix --installed "$formula"',
            "installed-formula guard")
    require(brew_seed, '"$selected_prefix"/opt/*|"$selected_prefix"/Cellar/*',
            "selected Homebrew prefix boundary")
    require(seed, "for candidate in m4 gm4 gnum4; do", "canonical GNU M4 fallback order")
    require(seed, "patsubst(", "GNU macro execution seed probe")
    require(helper, 'm4_link = seed_bin / "m4"', "literal M4 bootstrap shim")
    require(helper, '"AUTOCONF", "AUTOM4TE", "AUTOHEADER", "AUTORECONF"', "self-host isolation")
    require(helper, 'str(source / "bootstrap")', "source self-bootstrap")
    require(helper, '"install-binSCRIPTS"', "tool-only executable install")
    require(helper, '"install-dist_perllibDATA"', "Autom4te Perl library install")
    require(helper, '"install-nodist_pkgdataDATA"', "generated package-data install")
    require(helper, '"install-dist_autoconflibDATA"', "Autoconf source library install")
    require(helper, '"install-nodist_autoconflibDATA"', "Autoconf frozen library install")
    require(helper, '"install-nodist_autoscanlibDATA"', "Autoscan generated-data install")
    require(helper, '"install-dist_m4sugarlibDATA"', "M4sugar source library install")
    require(helper, '"install-nodist_m4sugarlibDATA"', "M4sugar frozen library install")
    require(helper, '"install-dist_autotestlibDATA"', "Autotest source library install")
    require(helper, '"install-nodist_autotestlibDATA"', "Autotest frozen library install")
    require(helper, '"install-dist_buildauxDATA"', "Autoconf build-aux install")
    require(helper, 'with tempfile.TemporaryDirectory(prefix="whp-autoconf-smoke-")', "runtime smoke workspace")
    require(helper, 'smoke_env.pop(key, None)', "seed-poison runtime isolation")
    require(helper, '"AC_INIT([whp-bootstrap-smoke],[1])', "installed runtime smoke")
    require(helper, '"pkgdata_DATA="', "documentation-free install override")
    for stale_target in (
        '"install-perllibDATA"',
        '"install-autoconflibDATA"',
        '"install-autoscanlibDATA"',
        '"install-m4sugarlibDATA"',
        '"install-autotestlibDATA"',
        '"install-buildauxDATA"',
    ):
        if stale_target in helper:
            raise SystemExit(
                f"error: stale collapsed Automake install target remains: {stale_target}"
            )
    require(
        config,
        "Option('BOOTSTRAP_AUTOCONF', 'Host features', 'Bootstrap/use WHP Autoconf'",
        "Autoconf menu option",
    )
    require(config, "'BOOTSTRAP_AUTOCONF',", "Autoconf shell export")

    order = [
        host_tools.index("BOOTSTRAP_AUTOMAKE=$(whp_normalize_auto_switch"),
        host_tools.index("BOOTSTRAP_AUTOCONF=$(whp_normalize_auto_switch"),
        host_tools.index("BOOTSTRAP_SED=$(whp_normalize_auto_switch"),
    ]
    if order != sorted(order) or len(set(order)) != len(order):
        raise SystemExit(
            "error: managed Autoconf is not ordered Automake -> Autoconf -> sed"
        )

    require(ledger, "``toolchains/autoconf``", "Autoconf registry row")
    require(ledger, "Autoconf bootstrap boundary", "Autoconf boundary")
    require(ledger, "seed Autoconf/autom4te", "Autoconf cycle guard")
    require(host_tools, "M4_PATH=", "Autoconf marker M4 promotion")
    require(host_tools, "export M4", "downstream GNU M4 export")
    require(host_tools, 'M4=$(/bin/sh "$SOURCE_DIR/seeds/gnum4.sh" --print-seed)',
            "installed Autoconf GNU M4 admission")
    require(host_tools, '[ "$AUTOCONF" != "$WHP_AUTOCONF_PREFIX/bin/autoconf" ]',
            "managed Autoconf M4 preservation")
    require(host_tools, '"$M4" --gnu --version', "promoted GNU M4 validation")
    require(host_tools, '"$M4" --gnu --fatal-warnings', "promoted M4 runtime probe")
    check_m4_runtime_guard()

    print("WHP Autoconf bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
