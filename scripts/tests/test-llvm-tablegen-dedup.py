#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
tablegen_path = Path(os.environ.get(
    'WHP_LLVM_TABLEGEN_CMAKE',
    ROOT / 'toolchains/llvm-project/llvm/cmake/modules/TableGen.cmake',
))
assert tablegen_path.is_file(), f'LLVM TableGen.cmake is unavailable: {tablegen_path}'
tablegen = tablegen_path.read_text(encoding='utf-8')

# Caller-supplied DEPENDS can repeat the same generated/tablegen prerequisite.
# Collapse exact repeats as soon as CMake parses them, preserving the first
# occurrence and every distinct dependency before add_custom_command sees them.
arg_dep_parse = 'cmake_parse_arguments(ARG "" "" "DEPENDS;EXTRA_INCLUDES" ${ARGN})'
arg_dep_dedup = 'list(REMOVE_DUPLICATES ARG_DEPENDS)'
assert arg_dep_parse in tablegen, 'TableGen DEPENDS argument parsing was removed'
assert arg_dep_dedup in tablegen, 'TableGen ARG_DEPENDS entries are not deduplicated'
assert tablegen.index(arg_dep_parse) < tablegen.index(arg_dep_dedup) < tablegen.index('add_custom_command(OUTPUT')

# TableGen include directories feed both command-line -I options and, on older
# CMake/Ninja combinations, fallback *.td globs. Repeated include directories
# therefore create redundant command text and dependency scans without adding
# any generated feature.
include_dedup = 'list(REMOVE_DUPLICATES tblgen_includes)'
assert include_dedup in tablegen, 'TableGen include directories are not deduplicated'
assert tablegen.index(include_dedup) < tablegen.index('list(TRANSFORM tblgen_includes PREPEND -I)')

# Keep both target-level and file-level TableGen dependencies because CMake does
# not propagate the file-level edge through custom targets. When both resolve to
# the same value, collapse the duplicate before add_custom_command sees it.
dep_set = 'set(tablegen_depends ${${project}_TABLEGEN_TARGET} ${tablegen_exe})'
dep_dedup = 'list(REMOVE_DUPLICATES tablegen_depends)'
assert dep_set in tablegen, 'TableGen target/executable dependency pair was removed'
assert dep_dedup in tablegen, 'TableGen target/executable dependencies are not deduplicated'
assert tablegen.index(dep_set) < tablegen.index(dep_dedup) < tablegen.index('add_custom_command(OUTPUT')

print('LLVM TableGen duplicate-edge policy: passed')
