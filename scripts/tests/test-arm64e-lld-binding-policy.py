#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard ARM64e Mach-O LLD admission against rebase-only false positives.

The native link probe is exercised on macOS with the selected Clang + ld64.lld.
This portable check guards its producer/consumer binding topology and the
pinned LLVM Mach-O decoder dependency; it is not a substitute for that link.
"""

from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[2]
probe = (ROOT / "scripts/whp-build/arm64e-lld-probe.bash").read_text(
    encoding="utf-8"
)
policy = (ROOT / "scripts/macos-arch-policy.bash").read_text(
    encoding="utf-8"
)
bootstrap = (ROOT / "scripts/bootstrap-native-clang.bash").read_text(
    encoding="utf-8"
)
decoder = (
    "lld/test/MachO/Inputs/arm64e-auth-metadata.py"
)
source = probe.split("cat > \"$probe_dir/consumer.s\" <<'ASM'", 1)[1].split(
    "\nASM\n", 1
)[0]

# The original local-rebase-only test remains active. The new consumer must
# contain *four* authenticated same-image rebases followed by four imported
# authenticated binds for all four PAC keys, diverse discriminator values,
# and address diversity on alternating slots. Order matters to the decoder.
assert "arm64e PAC probe: expected 4 authenticated rebases" in probe
expected = (
    ("ia", 42, True),
    ("ib", 513, False),
    ("da", 7, True),
    ("db", 65535, False),
)
slots = re.findall(
    r"^\.quad (_whp_auth_(?:local|external))@AUTH\((ia|ib|da|db),"
    r"(\d+)(,addr)?\)$",
    source, re.MULTILINE,
)
assert len(slots) == 8, slots
for index, (symbol, key, diversity, address) in enumerate(slots):
    assert symbol == ("_whp_auth_local" if index < 4
                      else "_whp_auth_external")
    exp_key, exp_div, exp_addr = expected[index % 4]
    assert (key, int(diversity), bool(address)) == (
        exp_key, exp_div, exp_addr
    )

assert ".globl _whp_auth_caller" in source
assert "bl _whp_auth_external" in source
assert 'cat > "$probe_dir/provider.s"' in probe
assert '"$probe_dir/provider.o" -o "$probe_dir/libwhp_auth_provider.dylib"' in probe
assert '-dylib -fixup_chains -install_name @rpath/libwhp_auth_consumer.dylib' in probe
assert '"$probe_dir/consumer.o" "$probe_dir/libwhp_auth_provider.dylib"' in probe
assert '-o "$probe_dir/libwhp_auth_consumer.dylib"' in probe
assert decoder in probe
assert '[[ ! -f "$auth_decoder" ]]' in probe
assert 'python3 "$auth_decoder" "$probe_dir/libwhp_auth_consumer.dylib"' in probe
assert "ARM64e LLD PAC imported bind or local rebase metadata invalid" in probe
assert "ARM64e LLD PAC consumer dylib bind link failed" in probe
assert "ARM64e LLD PAC consumer lost USERLAND24 or imported symbol" in probe
assert 'grep -Fq \'_whp_auth_external\'' in probe
assert 'grep -Fq \'DYLD_CHAINED_PTR_ARM64E_USERLAND24\'' in probe
assert "ARM64e LLD imported branch lost authenticated BRAA stub" in probe
assert "--section=__TEXT,__auth_stubs" in probe
assert "braa[[:space:]]+x16," in probe

# Every LLD selection path must still call the shared probe. On a failing
# imported bind, don't promote arm64e to the native Mach-O linker.
assert 'whp_bootstrap_arm64e_lld_auth_probe' in bootstrap
assert "whp-build/arm64e-lld-probe.bash" in bootstrap
assert policy.count("whp-build/arm64e-lld-probe.bash") == 2
assert 'WHP_ARM64E_USE_LLD' in policy

result = subprocess.run(
    ["bash", "-n", str(ROOT / "scripts/whp-build/arm64e-lld-probe.bash")],
    capture_output=True, text=True, check=False,
)
assert result.returncode == 0, result.stderr

print("ARM64e Mach-O LLD authenticated rebases/imported binds gate: verified")
