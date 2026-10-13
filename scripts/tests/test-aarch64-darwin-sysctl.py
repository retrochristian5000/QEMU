#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise the Darwin AArch64 feature-query helper on any C-capable host."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
CPUINFO = ROOT / "util" / "cpuinfo-aarch64.c"
src = CPUINFO.read_text(encoding="utf-8")
begin = src.index("static bool sysctl_for_bool(const char *name)")
end = src.index("\n#endif", begin)
function = src[begin:end]

# Compile the actual source helper with a mock macOS sysctlbyname. This
# covers its return-value and length guards without requiring an A18 Pro.
test_c = """
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdio.h>

static int scenario;
static int sysctlbyname(const char *name, void *value, size_t *len,
                        void *set, size_t setlen)
{
    (void)name;
    (void)set;
    (void)setlen;
    switch (scenario) {
    case 2:
        errno = ENOENT;
        return -1;
    case 3:
        errno = EINVAL;
        return -1;
    case 4:
        errno = EACCES;
        return -1;
    default:
        *(int *)value = (scenario != 1);
        *len = scenario == 5 ? sizeof(int) - 1 : sizeof(int);
        return 0;
    }
}
""" + function + """
int main(void)
{
    for (scenario = 0; scenario <= 5; ++scenario) {
        bool expected = scenario == 0;
        assert(sysctl_for_bool("hw.optional.arm.FEAT_CSSC") == expected);
    }
    puts("Darwin AArch64 ISA sysctl probe: passed");
    return 0;
}
"""

compiler = shlex.split(os.environ.get("CC_FOR_BUILD", "cc"))
if not compiler:
    raise SystemExit("empty host C compiler")
with tempfile.TemporaryDirectory(prefix="whp-aarch64-sysctl-") as work:
    program = Path(work) / "cpuinfo-test.c"
    executable = Path(work) / "cpuinfo-test"
    program.write_text(test_c, encoding="utf-8")
    subprocess.run(compiler + [
        "-std=c11", "-Wall", "-Wextra", "-Werror", str(program),
        "-o", str(executable)
    ], check=True)
    subprocess.run([str(executable)], check=True)
