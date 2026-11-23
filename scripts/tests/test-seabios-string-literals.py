#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import importlib.util
import pathlib
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "whp-build" / (
    "audit-seabios-string-literals.py"
)
SPEC = importlib.util.spec_from_file_location("rom_literals", SOURCE)
audit = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(audit)


class RomLiteralAuditTests(unittest.TestCase):
    def test_decodes_known_assembly_strings_without_interpreting_code(self):
        text = (
            '.section .rodata.str1.1,"aMS",@progbits,1\n'
            '.asciz "SeaBIOS"\n'
            '.ascii "hello\\000"\n'
            '.string "line\\nend"\n'
            '.byte 0x41\n'
            'movl $.Lstr, %eax\n'
        )
        self.assertEqual(
            list(audit.emitted_literals(text)),
            [b"SeaBIOS", b"hello\x00", b"line\nend"],
        )

    def test_ascii_directive_does_not_add_terminator(self):
        with tempfile.TemporaryDirectory() as temp:
            source = pathlib.Path(temp) / "code.s"
            source.write_text(
                '.ascii "raw"\\n.asciz "z"\\n.string "ab"\\n',
                encoding="utf-8",
            )
            reports, duplicates = audit.summarize(
                [("16bit", source)])
            self.assertEqual(reports, [("16bit", 3, 9)])
            self.assertEqual(duplicates, [])

    def test_counts_cross_mode_matches_without_claiming_saved_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            files = []
            samples = [
                '.asciz "same words"\n.asciz "16 only"\n',
                '.asciz "same words"\n.asciz "seg only"\n',
                '.asciz "flat only"\n',
            ]
            for i, data in enumerate(samples):
                path = pathlib.Path(temp) / ("code%d.s" % i)
                path.write_text(data, encoding="utf-8")
                files.append(path)
            report, repeats = audit.summarize(zip(
                ("16bit", "32seg", "32flat"), files))
            self.assertEqual(
                report,
                [("16bit", 2, 19), ("32seg", 2, 20), ("32flat", 1, 10)],
            )
            self.assertEqual(repeats, [(b"same words", {"16bit", "32seg"})])


if __name__ == "__main__":
    unittest.main()
