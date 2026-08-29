#!/usr/bin/env python3
"""Stage and repair the original 8086/8088 60h-6Fh Jcc aliases.

This helper is intentionally temporary: the matching workflow removes it after
proving the regression test fails before the decoder change and passes after it.
"""

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
TEST = ROOT / "tests/qtest/x86-16bit-test.c"
DECODE = ROOT / "target/i386/tcg/decode-original-x86.c.inc"

TEST_START = "        0xc6, 0x06, 0x02, 0x02, 0x01, /* phase = 1 */\n"
TEST_END = "        0xb0, 'T',                    /* mov al, 'T' */\n"
TEST_REPLACEMENT = """        0x31, 0xc0,                   /* xor ax, ax: ZF = 1 */
        0x64, 0x0b,                   /* 8086/8088 alias of JZ +0x0b */
        0xb0, 'F',                    /* wrong decode or untaken alias */
        0xeb, 0x0d,                   /* jmp output */
        0xb0, 'F',                    /* #UD handler: fail */
        0xeb, 0x09,                   /* jmp output */
        0x90, 0x90, 0x90,             /* keep success/fail offsets stable */
"""

OLD_DECODE = "    *entry = s->is_original_x86 && *b == 0x0f ? pop_cs : opcodes_root[*b];\n"
NEW_DECODE = """    if (s->is_original_x86) {
        if (*b == 0x0f) {
            *entry = pop_cs;
            return;
        }
        /*
         * The 8086/8088 decode 60h-6Fh as mirrors of the short conditional
         * branches at 70h-7Fh.  Reuse those entries so condition-code and
         * relative-branch semantics stay shared with the named Jcc opcodes.
         */
        if (*b >= 0x60 && *b <= 0x6f) {
            *entry = opcodes_root[*b + 0x10];
            return;
        }
    }
    *entry = opcodes_root[*b];
"""


def stage_test() -> None:
    text = TEST.read_text()
    if TEST_REPLACEMENT in text:
        return
    start = text.find(TEST_START)
    if start < 0:
        raise SystemExit("could not find old PUSHA/#UD regression block")
    end = text.find(TEST_END, start)
    if end < 0:
        raise SystemExit("could not find success marker after old regression block")
    TEST.write_text(text[:start] + TEST_REPLACEMENT + text[end:])


def apply_fix() -> None:
    text = DECODE.read_text()
    if NEW_DECODE in text:
        return
    if OLD_DECODE not in text:
        raise SystemExit("could not find original decode_root assignment")
    DECODE.write_text(text.replace(OLD_DECODE, NEW_DECODE, 1))


def main() -> None:
    if len(sys.argv) != 2 or sys.argv[1] not in {"test", "fix"}:
        raise SystemExit(f"usage: {Path(sys.argv[0]).name} test|fix")
    if sys.argv[1] == "test":
        stage_test()
    else:
        apply_fix()


if __name__ == "__main__":
    main()
