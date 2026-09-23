#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def require(text: str, needle: str, label: str) -> None:
    if needle not in text:
        raise SystemExit(f"error: missing {label}: {needle}")



def load_helper_module():
    path = ROOT / "scripts/ensure-bash.py"
    spec = importlib.util.spec_from_file_location("whp_ensure_bash", path)
    if spec is None or spec.loader is None:
        raise SystemExit("error: could not load ensure-bash.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_pinned_source_copy_ignores_dirty_checkout() -> None:
    helper = load_helper_module()
    if not hasattr(helper, "copy_bash_source"):
        raise SystemExit("error: Bash bootstrap has no isolated source-copy helper")

    with tempfile.TemporaryDirectory(prefix="whp-bash-source-copy-") as tmp:
        root = Path(tmp)
        source = root / "bash"
        destination = root / "copy"
        source.mkdir()
        subprocess.run(["git", "init", "-q", str(source)], check=True)
        subprocess.run(
            ["git", "-C", str(source), "config", "user.email", "whp@example.invalid"],
            check=True,
        )
        subprocess.run(
            ["git", "-C", str(source), "config", "user.name", "WHP Test"],
            check=True,
        )
        tracked = source / "configure"
        tracked.write_text("committed\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(source), "add", "configure"], check=True)
        subprocess.run(
            ["git", "-C", str(source), "commit", "-q", "-m", "fixture"],
            check=True,
        )
        revision = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
        ).stdout.strip()

        tracked.write_text("dirty working tree\n", encoding="utf-8")
        original = helper.SUBMODULE_DIR
        try:
            helper.SUBMODULE_DIR = source
            helper.copy_bash_source(revision, destination)
        finally:
            helper.SUBMODULE_DIR = original

        copied = (destination / "configure").read_text(encoding="utf-8")
        if copied != "committed\n":
            raise SystemExit(
                "error: Bash source copy used dirty working-tree contents"
            )
        if tracked.read_text(encoding="utf-8") != "dirty working tree\n":
            raise SystemExit("error: Bash source copy modified the checkout")

def main() -> int:
    gitmodules = (ROOT / ".gitmodules").read_text(encoding="utf-8")
    config = (ROOT / "scripts/whp-config/config.py").read_text(encoding="utf-8")
    build = (ROOT / "build.sh").read_text(encoding="utf-8")
    helper = (ROOT / "scripts/ensure-bash.py").read_text(encoding="utf-8")

    require(gitmodules, '[submodule "toolchains/bash"]', "Bash submodule")
    require(gitmodules, "path = toolchains/bash", "Bash submodule path")
    require(
        gitmodules,
        "url = https://github.com/retrochristian5000/bash.git",
        "WHP Bash fork URL",
    )
    require(gitmodules, "branch = master", "Bash fork branch")
    require(
        config,
        "Option('BOOTSTRAP_BASH', 'Host features', 'Bootstrap/use WHP Bash'",
        "Bash bootstrap menu policy",
    )
    require(config, "'BOOTSTRAP_BASH',", "Bash tri-state shell export")
    require(build, "BOOTSTRAP_BASH=", "Bash default policy")
    require(build, "scripts/ensure-bash.py", "Bash bootstrap hook")
    require(build, "WHP_BUILD_BASH_EXPLICIT", "explicit Bash override")
    require(helper, "toolchains/bash", "pinned Bash source")
    require(helper, '"submodule", "update"', "lazy Bash submodule initialization")
    require(helper, "BASH_GIT_COMMIT=", "Bash cache revision identity")
    require(helper, 'env.pop("INSTALL", None)', "INSTALL namespace isolation")
    require(helper, '"--without-bash-malloc"', "system malloc profile")
    require(helper, '"--disable-nls"', "minimal Bash profile")
    require(helper, '"-isysroot", sdkroot', "macOS Bash SDK routing")
    require(helper, "def copy_bash_source(", "isolated Bash source copy")
    require(helper, 'source_copy = work_dir / "source"', "Bash source workspace")
    require(helper, 'configure = source_copy / "configure"', "isolated configure input")
    if "bundled Bash submodule has tracked changes; commit them" in helper:
        raise SystemExit(
            "error: Bash bootstrap still rejects dirty working trees before "
            "using the pinned committed source"
        )
    test_pinned_source_copy_ignores_dirty_checkout()
    print("WHP Bash bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
