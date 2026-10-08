#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import struct
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


def test_macos_arch_identity() -> None:
    helper = load_helper_module()
    cases = {
        "arm64": "aarch64-apple-darwin25.0.0",
        "arm64e": "arm64e-apple-darwin25.0.0",
        "x86_64": "x86_64-apple-darwin25.0.0",
    }
    for arch, expected in cases.items():
        actual = helper.macos_host_triplet(arch, "25.0.0")
        if actual != expected:
            raise SystemExit(
                f"error: Bash host triplet mismatch for {arch}: "
                f"{actual} != {expected}"
            )

    expected_flags = [
        "-arch", "arm64e",
        "-isysroot", "/tmp/MacOSX.sdk",
        "-mmacosx-version-min=15.0",
    ]
    actual_flags = helper.macos_compile_flags(
        "/tmp/MacOSX.sdk", "arm64e", "15.0"
    )
    if actual_flags != expected_flags:
        raise SystemExit(
            "error: arm64e Bash compiler flags lost architecture/SDK policy"
        )

    try:
        helper.macos_host_triplet("arm64ec", "25.0.0")
    except RuntimeError:
        pass
    else:
        raise SystemExit("error: unsupported Bash ABI was accepted")


def test_arm64e_macho_subtype() -> None:
    helper = load_helper_module()
    with tempfile.TemporaryDirectory(prefix="whp-bash-arm64e-header-") as tmp:
        binary = Path(tmp) / "bash"
        cases = (
            ("arm64e", 0xFEEDFACF, 0x0100000C, 2, True),
            ("arm64e with capability bits", 0xFEEDFACF, 0x0100000C, 0x80000002, True),
            ("arm64 fallback", 0xFEEDFACF, 0x0100000C, 0, False),
            ("x86_64", 0xFEEDFACF, 0x01000007, 3, False),
            ("fat header", 0xCAFEBABE, 0x0100000C, 2, False),
        )
        for label, magic, cpu_type, cpu_subtype, expected in cases:
            binary.write_bytes(struct.pack("<III", magic, cpu_type, cpu_subtype))
            if helper.mach_o_is_arm64e(binary) != expected:
                raise SystemExit(f"error: Bash Mach-O subtype check: {label}")
        binary.write_bytes(b"\\xcf\\xfa")
        if helper.mach_o_is_arm64e(binary):
            raise SystemExit("error: truncated Bash Mach-O header was accepted")
        binary.unlink()
        if helper.mach_o_is_arm64e(binary):
            raise SystemExit("error: missing Bash Mach-O binary was accepted")


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
    build += (ROOT / "scripts/whp-build/host-tools.sh").read_text(encoding="utf-8")
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
    require(helper, 'BASH_BOOTSTRAP_SCHEMA = "4"', "Bash cache schema")
    require(helper, "BASH_GIT_COMMIT=", "Bash cache revision identity")
    require(helper, "BASH_HOST_TRIPLET=", "Bash host triplet cache identity")
    require(helper, "BASH_ABI_VARIANT=", "Bash ABI cache identity")
    require(helper, 'env.pop("INSTALL", None)', "INSTALL namespace isolation")
    require(helper, '"--without-bash-malloc"', "system malloc profile")
    require(helper, '"--disable-nls"', "minimal Bash profile")
    for option in (
        "--disable-readline",
        "--disable-history",
        "--disable-bang-history",
        "--disable-progcomp",
        "--disable-alias",
        "--disable-directory-stack",
        "--disable-coprocesses",
        "--disable-net-redirections",
        "--disable-restricted",
        "--disable-debugger",
        "--disable-function-import",
    ):
        require(helper, f'"{option}"', f"Bash lean profile {option}")
    require(
        helper,
        "BASH_REQUIRED_FEATURE_PROBE",
        "Bash required-feature runtime probe",
    )
    require(
        helper,
        "process-substitution",
        "Bash process-substitution feature guard",
    )
    require(
        helper,
        "whp_probe_array=(one two)",
        "Bash indexed-array feature guard",
    )
    require(helper, '"-isysroot", sdkroot', "macOS Bash SDK routing")
    require(helper, "def macos_arch_usable(", "macOS Bash ABI probe")
    require(helper, "def mach_o_is_arm64e(", "ARM64e binary subtype check")
    require(
        helper, 'arch != "arm64e" or mach_o_is_arm64e(bash_path)',
        "ARM64e cache executable guard",
    )
    require(helper, 'f"--build={host_triplet}"', "Bash build triplet routing")
    require(helper, 'f"--host={host_triplet}"', "Bash host triplet routing")
    require(helper, '"support" / "config.sub"', "Bash triplet canonicalization")
    require(helper, "bash_machtype(bash_path)", "Bash MACHTYPE validation")
    require(helper, "def copy_bash_source(", "isolated Bash source copy")
    require(helper, 'source_copy = work_dir / "source"', "Bash source workspace")
    require(helper, 'configure = source_copy / "configure"', "isolated configure input")
    if "bundled Bash submodule has tracked changes; commit them" in helper:
        raise SystemExit(
            "error: Bash bootstrap still rejects dirty working trees before "
            "using the pinned committed source"
        )
    test_macos_arch_identity()
    test_arm64e_macho_subtype()
    test_pinned_source_copy_ignores_dirty_checkout()
    print("WHP Bash bootstrap wiring: verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
