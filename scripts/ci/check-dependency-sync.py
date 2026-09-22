#!/usr/bin/env python3
"""Check dependency mirrors that Dependabot cannot update directly.

This keeps QEMU's Meson-side dependency pins synchronized with the package
manifests that Dependabot understands, without introducing a second source
of truth.
"""

from __future__ import annotations

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[2]


def norm_name(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def cargo_packages() -> dict[str, tuple[str, str | None]]:
    text = (ROOT / "rust" / "Cargo.lock").read_text(encoding="utf-8")
    packages: dict[str, tuple[str, str | None]] = {}
    for block in re.split(r"(?m)^\[\[package\]\]\s*$", text)[1:]:
        name = re.search(r'(?m)^name = "([^"]+)"$', block)
        version = re.search(r'(?m)^version = "([^"]+)"$', block)
        checksum = re.search(r'(?m)^checksum = "([^"]+)"$', block)
        if name and version:
            packages[name.group(1)] = (
                version.group(1),
                checksum.group(1) if checksum else None,
            )
    return packages


def check_rust_wraps(errors: list[str]) -> None:
    packages = cargo_packages()

    for path in sorted((ROOT / "subprojects").glob("*-rs.wrap")):
        text = path.read_text(encoding="utf-8")
        source = re.search(
            r"(?m)^source_url\s*=\s*https://crates\.io/api/v1/crates/"
            r"([^/]+)/([^/]+)/download\s*$",
            text,
        )
        if not source:
            continue

        name, wrap_version = source.groups()
        lock = packages.get(name)
        if lock is None:
            errors.append(f"{path.relative_to(ROOT)}: {name} is absent from rust/Cargo.lock")
            continue

        lock_version, lock_checksum = lock
        if wrap_version != lock_version:
            errors.append(
                f"{path.relative_to(ROOT)}: version {wrap_version} != "
                f"Cargo.lock {lock_version}"
            )

        wrap_hash = re.search(r"(?m)^source_hash\s*=\s*([0-9a-fA-F]+)\s*$", text)
        if wrap_hash and lock_checksum and wrap_hash.group(1).lower() != lock_checksum.lower():
            errors.append(
                f"{path.relative_to(ROOT)}: source_hash does not match "
                f"Cargo.lock checksum for {name} {lock_version}"
            )


def python_installed_versions() -> dict[str, set[str]]:
    text = (ROOT / "pythondeps.toml").read_text(encoding="utf-8")
    installed: dict[str, set[str]] = {}
    section = ""

    for line in text.splitlines():
        header = re.match(r"^\[([^]]+)\]\s*$", line)
        if header:
            section = header.group(1)
            continue

        entry = re.match(
            r'^\s*"?(?P<name>[^"\s=]+)"?\s*=\s*\{(?P<body>.*)\}\s*$',
            line,
        )
        if not entry:
            continue

        version = re.search(r'\binstalled\s*=\s*"([^"]+)"', entry.group("body"))
        if version:
            key = norm_name(entry.group("name"))
            installed.setdefault(key, set()).add(version.group(1))

    return installed


def check_python_mirrors(errors: list[str]) -> None:
    installed = python_installed_versions()

    for name, versions in sorted(installed.items()):
        if len(versions) > 1:
            errors.append(
                f"pythondeps.toml: {name} has conflicting installed versions: "
                + ", ".join(sorted(versions))
            )

    requirements = ROOT / "docs" / "requirements.txt"
    for line in requirements.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^\s*([A-Za-z0-9_.-]+)==([^\s#]+)", line)
        if not match:
            continue
        name, version = norm_name(match.group(1)), match.group(2)
        expected = installed.get(name)
        if expected and version not in expected:
            errors.append(
                f"docs/requirements.txt: {name}=={version} != "
                f"pythondeps.toml installed {', '.join(sorted(expected))}"
            )

    wheel_dir = ROOT / "python" / "wheels"
    wheel_re = re.compile(r"^(?P<name>.+?)-(?P<version>\d[^-]*)-")
    for path in sorted(wheel_dir.glob("*.whl")):
        match = wheel_re.match(path.name)
        if not match:
            errors.append(f"{path.relative_to(ROOT)}: cannot parse wheel name")
            continue

        name = norm_name(match.group("name"))
        version = match.group("version")
        expected = installed.get(name)
        if expected is None:
            errors.append(
                f"{path.relative_to(ROOT)}: vendored wheel has no installed pin "
                f"in pythondeps.toml"
            )
        elif version not in expected:
            errors.append(
                f"{path.relative_to(ROOT)}: wheel version {version} != "
                f"pythondeps.toml installed {', '.join(sorted(expected))}"
            )


def main() -> int:
    errors: list[str] = []
    check_rust_wraps(errors)
    check_python_mirrors(errors)

    if errors:
        print("Dependency synchronization errors:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1

    print("Dependency mirrors are synchronized.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
