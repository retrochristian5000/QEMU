#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from __future__ import annotations

import pathlib
import re
import shutil
import struct
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
HELPER = ROOT / 'scripts' / 'whp-build' / 'seabios-clang-gcc.bash'
SHF_MERGE = 0x10


def elf32_sections(path: pathlib.Path) -> dict[str, int]:
    data = path.read_bytes()
    if data[:6] != b'\x7fELF\x01\x01':
        raise AssertionError(f'expected little-endian ELF32: {path}')
    if struct.unpack_from('<H', data, 18)[0] != 3:
        raise AssertionError(f'expected EM_386: {path}')

    shoff = struct.unpack_from('<I', data, 32)[0]
    shentsize, shnum, shstrndx = struct.unpack_from('<HHH', data, 46)

    def section(index: int) -> tuple[int, ...]:
        offset = shoff + index * shentsize
        return struct.unpack_from('<IIIIIIIIII', data, offset)

    names_hdr = section(shstrndx)
    names = data[names_hdr[4]:names_hdr[4] + names_hdr[5]]

    def name_at(offset: int) -> str:
        end = names.find(b'\0', offset)
        if end < 0:
            end = len(names)
        return names[offset:end].decode('utf-8')

    result: dict[str, int] = {}
    for index in range(1, shnum):
        hdr = section(index)
        result[name_at(hdr[0])] = hdr[2]
    return result


def function_assembly(text: str, symbol: str) -> str:
    match = re.search(
        rf'^{re.escape(symbol)}:.*?^\.Lfunc_end[0-9]+:',
        text,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f'missing assembly body for {symbol}')
    return match.group(0)


class SeaBiosClangAbiTests(unittest.TestCase):
    def setUp(self):
        self.clang = shutil.which('clang')
        if not self.clang:
            self.skipTest('clang is unavailable')
        if not HELPER.is_file():
            self.fail(f'missing SeaBIOS Clang ABI helper: {HELPER}')

    def make_prefix(self, root: pathlib.Path) -> pathlib.Path:
        prefix = root / 'toolchain'
        (prefix / 'bin').mkdir(parents=True)
        (prefix / 'llvm' / 'bin').mkdir(parents=True)
        (prefix / 'bin' / 'i386-none-elf-gcc').write_bytes(HELPER.read_bytes())
        (prefix / 'bin' / 'i386-none-elf-gcc').chmod(0o755)
        (prefix / 'llvm' / 'bin' / 'clang').symlink_to(self.clang)
        return prefix

    def compile(self, compiler: pathlib.Path, source: pathlib.Path,
                output: pathlib.Path, *extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run([
            str(compiler), '-m32', '-march=i386', '-ffreestanding',
            '-fno-pic', '-fno-pie', *extra,
            '-c', str(source), '-o', str(output),
        ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)

    def test_no_merge_constants_removes_elf_merge_semantics(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prefix = self.make_prefix(root)
            compiler = prefix / 'bin' / 'i386-none-elf-gcc'
            source = root / 'constants.c'
            source.write_text(
                'const char *first(void) { return "SeaBIOS ABI"; }\n'
                'const char *second(void) { return "SeaBIOS ABI"; }\n',
                encoding='utf-8',
            )

            unmerged = root / 'unmerged.o'
            result = self.compile(
                compiler, source, unmerged,
                '-Os', '-fdata-sections', '-fno-merge-constants',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            rodata = {
                name: flags for name, flags in elf32_sections(unmerged).items()
                if name.startswith('.rodata')
            }
            self.assertTrue(rodata)
            self.assertTrue(all(not (flags & SHF_MERGE) for flags in rodata.values()), rodata)

            merged = root / 'merged.o'
            result = self.compile(
                compiler, source, merged,
                '-Os', '-fdata-sections', '-fno-merge-constants',
                '-fmerge-constants',
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            merged_rodata = {
                name: flags for name, flags in elf32_sections(merged).items()
                if name.startswith('.rodata')
            }
            self.assertTrue(any(flags & SHF_MERGE for flags in merged_rodata.values()), merged_rodata)

    def test_no_merge_constants_preserves_make_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prefix = self.make_prefix(root)
            compiler = prefix / 'bin' / 'i386-none-elf-gcc'
            source = root / 'dependency.c'
            output = root / 'dependency.o'
            source.write_text('int dependency(void) { return 1; }\n', encoding='utf-8')
            result = self.compile(
                compiler, source, output,
                '-fno-merge-constants', '-MD', '-MT', str(output),
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            depfile = root / 'dependency.d'
            self.assertTrue(depfile.is_file())
            dependencies = depfile.read_text(encoding='utf-8')
            self.assertIn(str(output), dependencies)
            self.assertIn(str(source), dependencies)

    def test_i386_calling_convention_and_16bit_codegen(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prefix = self.make_prefix(root)
            compiler = prefix / 'bin' / 'i386-none-elf-gcc'
            source = root / 'abi.c'
            asm = root / 'abi.s'
            source.write_text(
                'struct pair { int lo; int hi; };\n'
                '__attribute__((noinline)) struct pair make_pair(int lo, int hi) {\n'
                '  struct pair p = { lo, hi }; return p;\n'
                '}\n'
                'extern int sink4(int, int, int, int);\n'
                '__attribute__((noinline)) int call4(int a, int b, int c, int d) {\n'
                '  return sink4(a, b, c, d);\n'
                '}\n'
                '_Static_assert(sizeof(void *) == 4, "i386 pointers must be 32 bit");\n',
                encoding='utf-8',
            )
            result = subprocess.run([
                str(compiler), '-m32', '-m16', '-march=i386', '-mregparm=3',
                '-mpreferred-stack-boundary=2', '-freg-struct-return',
                '-fno-defer-pop', '-fno-merge-constants',
                '-ffreestanding', '-fno-pic', '-fno-pie',
                '-O0', '-S', str(source), '-o', str(asm),
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            text = asm.read_text(encoding='utf-8')
            self.assertIn('.code16', text)

            pair = function_assembly(text, 'make_pair')
            self.assertIn('%eax', pair)
            self.assertIn('%edx', pair)

            call = function_assembly(text, 'call4')
            self.assertIn('%eax', call)
            self.assertIn('%edx', call)
            self.assertIn('%ecx', call)
            self.assertRegex(call, r'(pushl[^\n]+|movl[^\n]+,[ \t]*\(%esp\))')
            self.assertRegex(call, r'calll?[ \t]+sink4[^\n]*\n[ \t]*addl[ \t]+\$[0-9]+,[ \t]*%esp')

    def test_whole_program_probe_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            prefix = self.make_prefix(root)
            compiler = prefix / 'bin' / 'i386-none-elf-gcc'
            result = subprocess.run([
                str(compiler), '-fwhole-program', '-S', '-o', '/dev/null',
                '-xc', '/dev/null',
            ], text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('whole-program optimization is unsupported', result.stderr)


if __name__ == '__main__':
    unittest.main()
