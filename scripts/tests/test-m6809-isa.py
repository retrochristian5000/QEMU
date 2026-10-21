#!/usr/bin/env python3
"""MC6809 ISA regression: independent Motorola appendix C/F samples."""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ISA = ROOT / "scripts" / "m6809_isa.py"
spec = importlib.util.spec_from_file_location("m6809_isa", ISA)
isa = importlib.util.module_from_spec(spec)
spec.loader.exec_module(isa)

examples = [
    ("12", ("NOP", "inherent", 1, 0x12)),
    ("16 FF FE", ("LBRA", "relative16", 3, 0x16)),
    ("20 FE", ("BRA", "relative8", 2, 0x20)),
    ("10 26 01 23", ("LBNE", "relative16", 4, 0x1026)),
    ("10 8E 12 34", ("LDY", "immediate16", 4, 0x108E)),
    ("11 83 00 01", ("CMPU", "immediate16", 4, 0x1183)),
    ("10 3F", ("SWI2", "inherent", 2, 0x103f)),
    ("11 3F", ("SWI3", "inherent", 2, 0x113f)),
    ("3B", ("RTI", "inherent", 1, 0x3b)),
    ("1E 12", ("EXG", "register_postbyte", 2, 0x1e)),
    ("8D FE", ("BSR", "relative8", 2, 0x8d)),
    ("A6 84", ("LDA", "indexed", 2, 0xa6)),
    ("A6 88 7F", ("LDA", "indexed", 3, 0xa6)),
    ("A6 89 12 34", ("LDA", "indexed", 4, 0xa6)),
    ("A6 9F 12 34", ("LDA", "indexed", 4, 0xa6)),
    ("10 AE 88 FE", ("LDY", "indexed", 4, 0x10ae)),
    ("FD 12 34", ("STD", "extended", 3, 0xfd)),
]
for code, expected in examples:
    result = isa.decode(bytes.fromhex(code))
    assert result == expected, (code, result, expected)

illegal = ["01", "02", "05", "4E", "5E", "87 FF", "CD 00", "8F 00",
           "10", "11", "10 20 00 00", "11 26 00 00", "10 87 00",
           "A6 87", "A6 8A", "A6 8F 00 00", "A6 90", "A6 92",
           "A6 97", "A6 9E", "A6 BF 00 00", "10 8E 00", "A6 89 00"]
for code in illegal:
    assert isa.decode(bytes.fromhex(code)) is None, code

for postbyte in range(0x80):
    assert isa.indexed_extra(postbyte) == 0, hex(postbyte)
assert isa.indexed_extra(0x88) == 1
assert isa.indexed_extra(0x89) == 2
assert isa.indexed_extra(0x9c) == 1
assert isa.indexed_extra(0x9d) == 2
assert isa.indexed_extra(0x9f) == 2
assert isa.indexed_extra(0x80) == 0
assert isa.indexed_extra(0x91) == 0
assert isa.indexed_extra(0x93) == 0
for pb in (0x87, 0x8a, 0x8e, 0x8f, 0x90, 0x92, 0x97, 0x9a, 0x9e, 0xbf):
    assert isa.indexed_extra(pb) is None, hex(pb)

assert len(isa.OPCODES) == 268
assert set(isa.OPCODES).isdisjoint({0x10, 0x11, 0x1020, 0x1120})
assert all(x.length >= (2 if key > 255 else 1) for key, x in isa.OPCODES.items())
print(f"MC6809 ISA reference: {len(isa.OPCODES)} legal opcodes, "
      f"{len(examples)} decoded samples, {len(illegal)} illegal/truncation checks passed")
