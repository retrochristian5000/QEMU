#!/usr/bin/env python3
"""MC6809/MC6809E opcode legality and instruction-length reference.

Motorola M6809PM/AD (1981), appendix C opcode listings and appendix F indexed
postbytes. This is metadata for audit/tests, NOT an executing QEMU CPU target.
The HD6309 extended instruction set is intentionally excluded.
"""
from __future__ import annotations

import argparse
import json
from typing import NamedTuple


class Instruction(NamedTuple):
    mnemonic: str
    mode: str
    length: int                 # minimum bytes, including opcode/prefix


OPCODES: dict[int, Instruction] = {}


def add(code: int, name: str, mode: str, length: int) -> None:
    if code in OPCODES:
        raise AssertionError(f"duplicate MC6809 opcode {code:04x}")
    OPCODES[code] = Instruction(name, mode, length)


# Main opcode page. 10h and 11h are prefixes, not standalone instructions.
for low, name in {
    0x0: "NEG", 0x3: "COM", 0x4: "LSR", 0x6: "ROR", 0x7: "ASR",
    0x8: "ASL", 0x9: "ROL", 0xa: "DEC", 0xc: "INC", 0xd: "TST",
    0xe: "JMP", 0xf: "CLR",
}.items():
    for base, mode, length in (
        (0x00, "direct", 2), (0x60, "indexed", 2),
        (0x70, "extended", 3),
    ):
        add(base + low, name, mode, length)
    if low != 0xe:              # no JMP accumulator opcode
        for base, reg in ((0x40, "A"), (0x50, "B")):
            add(base + low, name + reg, "inherent", 1)

for code, name, mode, length in (
    (0x12, "NOP", "inherent", 1), (0x13, "SYNC", "inherent", 1),
    (0x16, "LBRA", "relative16", 3), (0x17, "LBSR", "relative16", 3),
    (0x19, "DAA", "inherent", 1), (0x1a, "ORCC", "immediate8", 2),
    (0x1c, "ANDCC", "immediate8", 2), (0x1d, "SEX", "inherent", 1),
    (0x1e, "EXG", "register_postbyte", 2),
    (0x1f, "TFR", "register_postbyte", 2),
    (0x34, "PSHS", "stack_mask", 2), (0x35, "PULS", "stack_mask", 2),
    (0x36, "PSHU", "stack_mask", 2), (0x37, "PULU", "stack_mask", 2),
    (0x39, "RTS", "inherent", 1), (0x3a, "ABX", "inherent", 1),
    (0x3b, "RTI", "inherent", 1), (0x3c, "CWAI", "immediate8", 2),
    (0x3d, "MUL", "inherent", 1), (0x3f, "SWI", "inherent", 1),
):
    add(code, name, mode, length)

branches = (
    "BRA", "BRN", "BHI", "BLS", "BCC", "BCS", "BNE", "BEQ",
    "BVC", "BVS", "BPL", "BMI", "BGE", "BLT", "BGT", "BLE",
)
for i, name in enumerate(branches):
    add(0x20 + i, name, "relative8", 2)
    if i:                       # LBRA is 16h, not 10 20h
        add(0x1020 + i, "L" + name, "relative16", 4)
for i, name in enumerate(("LEAX", "LEAY", "LEAS", "LEAU")):
    add(0x30 + i, name, "indexed", 2)

accumulator_a = (
    "SUBA", "CMPA", "SBCA", "SUBD", "ANDA", "BITA", "LDA", None,
    "EORA", "ADCA", "ORA", "ADDA", "CMPX", "BSR", "LDX", None,
)
accumulator_b = (
    "SUBB", "CMPB", "SBCB", "ADDD", "ANDB", "BITB", "LDB", None,
    "EORB", "ADCB", "ORB", "ADDB", "LDD", None, "LDU", None,
)
for high, row in ((0x80, accumulator_a), (0xc0, accumulator_b)):
    for page, mode, length in (
        (0x00, "immediate", 2), (0x10, "direct", 2),
        (0x20, "indexed", 2), (0x30, "extended", 3),
    ):
        for nibble, mnemonic in enumerate(row):
            name = mnemonic
            if page:
                if high == 0x80 and nibble == 7:
                    name = "STA"
                elif high == 0x80 and nibble == 13:
                    name = "JSR"
                elif high == 0x80 and nibble == 15:
                    name = "STX"
                elif high == 0xc0 and nibble == 7:
                    name = "STB"
                elif high == 0xc0 and nibble == 13:
                    name = "STD"
                elif high == 0xc0 and nibble == 15:
                    name = "STU"
            if name is None:
                continue
            if high == 0x80 and page == 0 and nibble == 13:
                actual_mode, actual_len = "relative8", 2
            elif page == 0 and nibble in (3, 12, 14):
                actual_mode, actual_len = "immediate16", 3
            else:
                actual_mode = mode + "8" if page == 0 else mode
                actual_len = length
            add(high + page + nibble, name, actual_mode, actual_len)

# Page 2 (10h prefix) and page 3 (11h prefix).
for code, name, mode, length in (
    (0x103f, "SWI2", "inherent", 2),
    (0x1083, "CMPD", "immediate16", 4),
    (0x108c, "CMPY", "immediate16", 4),
    (0x108e, "LDY", "immediate16", 4),
    (0x10ce, "LDS", "immediate16", 4),
    (0x113f, "SWI3", "inherent", 2),
    (0x1183, "CMPU", "immediate16", 4),
    (0x118c, "CMPS", "immediate16", 4),
):
    add(code, name, mode, length)
for prefix, register_group in (
    (0x1000, ((3, "CMPD"), (12, "CMPY"), (14, "LDY"), (15, "STY"))),
    (0x1100, ((3, "CMPU"), (12, "CMPS"))),
):
    for offset, mode, length in (
        (0x90, "direct", 3), (0xa0, "indexed", 3),
        (0xb0, "extended", 4),
    ):
        for nibble, name in register_group:
            add(prefix + offset + nibble, name, mode, length)
for base, mode, length in (
    (0x10d0, "direct", 3), (0x10e0, "indexed", 3),
    (0x10f0, "extended", 4),
):
    add(base + 14, "LDS", mode, length)
    add(base + 15, "STS", mode, length)


def indexed_extra(postbyte: int) -> int | None:
    """Return following displacement bytes, or None for illegal MC6809 mode.

    A legal postbyte need not be valid for all opcodes (e.g. LEA indirect
    constraints); instruction-specific execution checks belong to a CPU core.
    """
    if not 0 <= postbyte <= 255:
        return None
    if not postbyte & 0x80:     # 5-bit signed offset from X/Y/U/S
        return 0
    nibble = postbyte & 0x0f
    indirect = bool(postbyte & 0x10)
    if nibble in (7, 10, 14):
        return None
    if nibble == 15:           # only [extended] = 9fh exists
        return 2 if postbyte == 0x9f else None
    if indirect and nibble in (0, 2):  # [,R+] and [,-R] forbidden
        return None
    if nibble in (8, 12):
        return 1
    if nibble in (9, 13):
        return 2
    return 0


class Decoded(NamedTuple):
    mnemonic: str
    mode: str
    length: int
    opcode: int


def decode(data: bytes) -> Decoded | None:
    """Decode opcode + addressing length; None for illegal/truncated bytes.

    This does not execute instructions or validate instruction-specific
    register postbytes, flag changes, interrupts, or timing.
    """
    if not data:
        return None
    first = data[0]
    if first in (0x10, 0x11):
        if len(data) < 2:
            return None
        code = (first << 8) | data[1]
    else:
        code = first
    insn = OPCODES.get(code)
    if insn is None:
        return None
    length = insn.length
    if insn.mode == "indexed":
        postbyte_at = 2 if code > 255 else 1
        if len(data) <= postbyte_at:
            return None
        extra = indexed_extra(data[postbyte_at])
        if extra is None:
            return None
        length += extra
    if len(data) < length:
        return None
    return Decoded(insn.mnemonic, insn.mode, length, code)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--list", action="store_true", help="emit legal ISA opcode metadata as JSON")
    parser.add_argument("--decode", metavar="HEX", help="decode a hex byte stream")
    args = parser.parse_args()
    if args.list:
        print(json.dumps({f"{code:02X}": insn._asdict() for code, insn in sorted(OPCODES.items())}, indent=2))
    elif args.decode is not None:
        try:
            raw = bytes.fromhex(args.decode)
        except ValueError as exc:
            parser.error(str(exc))
        value = decode(raw)
        print(json.dumps(value._asdict() if value else None))
    else:
        print(f"MC6809 documented legal instructions: {len(OPCODES)}; no QEMU CPU target")


if __name__ == "__main__":
    main()
