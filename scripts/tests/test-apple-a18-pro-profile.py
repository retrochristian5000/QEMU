#!/usr/bin/env python3
"""Audit the pinned LLVM Apple A18 Pro ISA profile against Darwin evidence."""

import argparse
import json
from pathlib import Path
import platform
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "toolchains/llvm-project/llvm/lib/Target/AArch64/AArch64Processors.td"
HOST = ROOT / "toolchains/llvm-project/llvm/lib/TargetParser/Host.cpp"
A18_PRO_FAMILY = 0x75D4ACB9

# LLVM's feature names mapped to the Darwin sysctls already used by Host.cpp.
# An absent sysctl reports UNKNOWN, not false.
CHECKS = {
    "FeatureSME": "hw.optional.arm.FEAT_SME",
    "FeatureSME2": "hw.optional.arm.FEAT_SME2",
    "FeatureBF16": "hw.optional.arm.FEAT_BF16",
    "FeatureMatMulInt8": "hw.optional.arm.FEAT_I8MM",
    "FeatureLSE": "hw.optional.arm.FEAT_LSE",
    "FeaturePAuth": "hw.optional.arm.FEAT_PAuth",
}
# These are not implied by Armv9.2-A, ordinary arm64e, or Apple's SME support.
UNPROVEN = ("FeatureSVE", "FeatureSVE2", "FeatureSMEFA64",
            "FeatureMOPS", "FeaturePAuthLR")


def sysctl(name):
    result = subprocess.run(["sysctl", "-n", name], capture_output=True,
                            text=True, check=False)
    if result.returncode:
        return None
    try:
        return int(result.stdout.strip(), 0)
    except ValueError:
        try:
            return int(result.stdout.strip(), 10)
        except ValueError:
            return None


def source_profile():
    text = PROFILE.read_text(encoding="utf-8")
    host = HOST.read_text(encoding="utf-8")
    m = re.search(r"list<SubtargetFeature> AppleM4\s*=\s*\[(.*?)\];",
                  text, re.S)
    if not m:
        raise ValueError("AppleM4 feature list not found")
    if not re.search(r"AppleA18\s*=\s*AppleM4\s*;", text):
        raise ValueError("A18 CPU feature baseline changed: review required")
    if not re.search(r"AppleA18Pro\s*=\s*AppleA18\s*;", text):
        raise ValueError("A18 Pro feature baseline changed: review required")
    features = set(re.findall(r"\b(?:Feature\w+|HasV\w+)\b", m.group(1)))
    required = {"HasV9_2aOps", "FeatureSME", "FeatureSME2", "FeaturePAuth"}
    if not required <= features:
        raise ValueError("A18 Pro feature baseline changed")
    unproven = features.intersection(UNPROVEN)
    if unproven:
        raise ValueError(f"Unverified A18 Pro extensions: {sorted(unproven)}")
    mapping = (r'case\s+0x75d4acb9\s*:\s*//\s*TAHITI: A18 Pro'
               r'\s*return\s+"apple-a18-pro";')
    if not re.search(mapping, host):
        raise ValueError("A18 Pro Darwin CPU family mapping changed")
    return features


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--hardware-only", action="store_true",
                        help="probe Darwin without the pinned LLVM submodule")
    args = parser.parse_args()
    features = None if args.hardware_only else source_profile()
    report = {
        "profile": "apple-a18-pro",
        "profile_features": sorted(features) if features is not None else None,
        "host_family": None,
        "host_isa_features": {},
        "contradictions": [],
    }
    if sys.platform == "darwin" and platform.machine() == "arm64":
        family = sysctl("hw.cpufamily")
        report["host_family"] = f"0x{family:08x}" if family is not None else None
        if family == A18_PRO_FAMILY:
            for feature, key in CHECKS.items():
                value = sysctl(key)
                report["host_isa_features"][feature] = value
                if value == 0 and features is not None and feature in features:
                    report["contradictions"].append(feature)
    print(json.dumps(report, indent=2))
    if report["contradictions"]:
        parser.exit(1, "A18 Pro profile contradicts disabled Darwin ISA features\n")


if __name__ == "__main__":
    main()
