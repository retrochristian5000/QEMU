#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import os
from pathlib import Path
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
tablegen_path = Path(os.environ.get(
    'WHP_LLVM_TABLEGEN_CMAKE',
    ROOT / 'toolchains/llvm-project/llvm/cmake/modules/TableGen.cmake',
))
assert tablegen_path.is_file(), f'LLVM TableGen.cmake is unavailable: {tablegen_path}'
tablegen = tablegen_path.read_text(encoding='utf-8')

# The complete TableGen prerequisite set must be deduplicated once after all
# dependency sources are combined, not separately before the final command.
parse = 'cmake_parse_arguments(ARG "" "" "DEPENDS;EXTRA_INCLUDES" ${ARGN})'
assert parse in tablegen, 'TableGen DEPENDS argument parsing is missing'

include_dedup = 'list(REMOVE_DUPLICATES tblgen_includes)'
assert include_dedup in tablegen, 'TableGen include directories are not deduplicated'
assert tablegen.index(include_dedup) < tablegen.index(
    'list(TRANSFORM tblgen_includes PREPEND -I)'
)

start = tablegen.index('  set(tablegen_depends\n')
end = tablegen.index('\n\n  if(LLVM_PARALLEL_TABLEGEN_JOBS)', start)
block = tablegen[start:end]
for required in (
    '${ARG_DEPENDS}',
    '${${project}_TABLEGEN_TARGET}',
    '${tablegen_exe}',
    '${global_tds}',
    '${LLVM_TARGET_DEFINITIONS_ABSOLUTE}',
    '${LLVM_TARGET_DEPENDS}',
    'list(REMOVE_ITEM tablegen_depends "")',
    'list(REMOVE_DUPLICATES tablegen_depends)',
):
    assert required in block, f'TableGen combined dependency edge missing: {required}'
assert block.index('list(REMOVE_ITEM tablegen_depends "")') < block.index(
    'list(REMOVE_DUPLICATES tablegen_depends)'
)
assert tablegen.index(parse) < start < tablegen.index('add_custom_command(OUTPUT')
assert tablegen.count('list(REMOVE_DUPLICATES tablegen_depends)') == 1
assert 'list(REMOVE_DUPLICATES ARG_DEPENDS)' not in tablegen
command = tablegen.split('  add_custom_command(OUTPUT ', 1)[1].split(
    '  # \`make clean\`', 1
)[0]
assert 'DEPENDS ${tablegen_depends}' in command
assert 'DEPENDS ${ARG_DEPENDS}' not in command

# Exercise the extracted, actual LLVM CMake logic rather than an independent
# Python reimplementation. Repeated caller, fallback, input, and target
# dependencies collapse; distinct target and executable edges survive.
def cmake_case(target, executable, caller, fallback, source, extra, expected):
    settings = {
        "project": "LLVM",
        "LLVM_TABLEGEN_TARGET": target,
        "tablegen_exe": executable,
        "ARG_DEPENDS": caller,
        "global_tds": fallback,
        "LLVM_TARGET_DEFINITIONS_ABSOLUTE": source,
        "LLVM_TARGET_DEPENDS": extra,
    }
    setup = "\n".join(f'set({name} "{value}")' for name, value in settings.items())
    check = (
        'if(NOT "${tablegen_depends}" STREQUAL "' + expected + '")\n'
        '  message(FATAL_ERROR "wrong TableGen dependencies: ${tablegen_depends}")\n'
        'endif()\n'
    )
    return setup + "\n" + block + "\n" + check


script = (
    cmake_case(
        "tblgen", "tblgen",
        "/tmp/a.td;/tmp/b.td;/tmp/a.td",
        "/tmp/a.td;/tmp/c.td;/tmp/b.td",
        "/tmp/a.td", "/tmp/c.td;/tmp/d.td",
        "/tmp/a.td;/tmp/b.td;tblgen;/tmp/c.td;/tmp/d.td",
    )
    + cmake_case(
        "tblgen-host", "/tmp/tblgen",
        "/tmp/a.td;/tmp/a.td", "",
        "/tmp/a.td", "",
        "/tmp/a.td;tblgen-host;/tmp/tblgen",
    )
)
with tempfile.TemporaryDirectory(prefix="whp-llvm-tablegen-") as directory:
    test_file = Path(directory) / "dependencies.cmake"
    test_file.write_text(script, encoding="utf-8")
    result = subprocess.run(
        ["cmake", "-P", str(test_file)],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr

print('LLVM TableGen combined duplicate-edge policy: passed')
