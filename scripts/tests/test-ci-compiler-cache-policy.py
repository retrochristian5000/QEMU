#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Verify CI cache publication, compiler provenance, and restore boundaries."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SAVE_CONDITION = (
    "success() && github.event_name == 'push' && "
    "github.ref == 'refs/heads/master' && "
    "steps.ccache-restore.outputs.cache-hit != 'true'"
)
POLICIES = {
    ".github/workflows/ci.yml": (
        "whp-qemu-ccache-v2-${{ runner.os }}-${{ runner.arch }}-"
        "${{ matrix.target }}-",
        ".ccache",
    ),
    ".github/workflows/macos-lto-repro.yml": (
        "whp-macos-lto-ccache-v2-${{ runner.os }}-${{ runner.arch }}-",
        ".whp-compiler-cache",
    ),
}


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def workflow_step(source: str, name: str) -> str:
    """Extract exactly one named workflow step without YAML dependencies."""
    lines = source.splitlines()
    heading = f"      - name: {name}"
    positions = [index for index, line in enumerate(lines) if line == heading]
    require(len(positions) == 1, f"{name}: expected exactly one step")
    start = positions[0]
    end = next(
        (index for index in range(start + 1, len(lines))
         if lines[index].startswith("      - ")),
        len(lines),
    )
    return "\n".join(lines[start:end])


def step_field(step: str, name: str) -> str:
    values = [
        line.strip().removeprefix(f"{name}: ").strip()
        for line in step.splitlines()
        if line.strip().startswith(f"{name}: ")
    ]
    require(len(values) == 1, f"{name}: expected exactly one value")
    return values[0]


def check_workflow(relative_path: str, source: str,
                   cache_prefix: str, cache_path: str) -> None:
    require("      CCACHE_COMPILERCHECK: content" in source,
            f"{relative_path}: compiler content identity missing")
    require(
        "run: python3 scripts/tests/test-ci-compiler-cache-policy.py" in source,
        f"{relative_path}: policy test is not wired into CI",
    )
    restore = workflow_step(source, "Restore compiler cache")
    save = workflow_step(source, "Save compiler cache")
    require("actions/cache/restore@" in restore,
            f"{relative_path}: restore must not implicitly save")
    require("actions/cache/save@" in save,
            f"{relative_path}: expected an explicit save step")
    require(step_field(save, "if") == SAVE_CONDITION,
            f"{relative_path}: cache may be published on a failed or untrusted run")
    require(step_field(restore, "path") == cache_path,
            f"{relative_path}: unexpected cache restore path")
    require(step_field(save, "path") == cache_path,
            f"{relative_path}: cache save and restore paths disagree")
    expected_key = cache_prefix + "${{ github.sha }}"
    require(step_field(restore, "key") == expected_key,
            f"{relative_path}: invalid restore cache generation")
    require(step_field(save, "key") == expected_key,
            f"{relative_path}: saved cache has a different identity")
    require("          restore-keys:\n            " + cache_prefix in restore,
            f"{relative_path}: fallback cache could cross a policy generation")
    require("-ccache-v1-" not in restore + save,
            f"{relative_path}: legacy cache generation is still admitted")


def check_negative_controls(relative_path: str, source: str,
                            cache_prefix: str, cache_path: str) -> None:
    """The checker must fail if a dangerous policy is reintroduced."""
    variants = (
        ("unconditional save", source.replace(
            "if: " + SAVE_CONDITION,
            "if: always() && steps.ccache-restore.outputs.cache-hit != 'true'",
        )),
        ("timestamp-only compiler identity", source.replace(
            "CCACHE_COMPILERCHECK: content", "CCACHE_COMPILERCHECK: mtime",
        )),
        ("legacy cache fallback", source.replace(
            cache_prefix, cache_prefix.replace("-v2-", "-v1-"),
        )),
    )
    for description, changed in variants:
        require(changed != source,
                f"{relative_path}: ineffective negative fixture {description}")
        try:
            check_workflow(relative_path, changed, cache_prefix, cache_path)
        except AssertionError:
            continue
        raise AssertionError(f"{relative_path}: accepted {description}")


def main() -> int:
    for relative_path, (cache_prefix, cache_path) in POLICIES.items():
        source = (ROOT / relative_path).read_text(encoding="utf-8")
        check_workflow(relative_path, source, cache_prefix, cache_path)
        check_negative_controls(relative_path, source, cache_prefix, cache_path)
        print(f"WHP compiler-cache policy: verified {relative_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
