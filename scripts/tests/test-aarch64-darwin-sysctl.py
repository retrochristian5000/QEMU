#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Exercise Darwin AArch64 feature and cache queries on any C-capable host."""

import os
from pathlib import Path
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
src = (ROOT / "util/cpuinfo-aarch64.c").read_text(encoding="utf-8")
begin = src.index("static bool sysctl_for_feature(")
end = src.index("\n#endif", begin)
feature = src[begin:end]

src = (ROOT / "util/cacheflush.c").read_text(encoding="utf-8")
begin = src.index("static void sys_cache_info(", src.index("#elif defined(CONFIG_DARWIN)"))
end = src.index("\n#elif", begin)
cache = src[begin:end]

test_c = """
#include <assert.h>
#include <errno.h>
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <limits.h>
#include <stdio.h>
#include <string.h>

static int scenario, legacy_calls;
static int sysctlbyname(const char *name, void *value, size_t *len,
                        void *set, size_t setlen)
{
    (void)set;
    (void)setlen;
    if (!strcmp(name, "hw.cachelinesize")) {
        int64_t size = 128;
        assert(*len == sizeof(size));
        switch (scenario) {
        case 1: size = 64; break;
        case 2: size = 0; break;
        case 3: size = 96; break;
        case 4: size = -128; break;
        case 5: size = (int64_t)INT_MAX + 1; break;
        case 6: *len = 4; break;
        case 7: errno = ENOENT; return -1;
        case 8: size = 1; break;
        }
        memcpy(value, &size, *len);
        return 0;
    }
    if (!strcmp(name, "hw.optional.armv8_1_atomics")) {
        legacy_calls++;
        if (scenario == 7) {
            errno = ENOENT;
            return -1;
        }
        *(int *)value = scenario == 8 ? 0 : 1;
        *len = scenario == 9 ? sizeof(int) - 1 : sizeof(int);
        return 0;
    }
    switch (scenario) {
    case 2: case 7: case 8: case 9:
        errno = ENOENT;
        return -1;
    case 3:
        errno = EINVAL;
        return -1;
    case 4:
        errno = EACCES;
        return -1;
    default:
        *(int *)value = scenario == 6 ? 2 : scenario != 1;
        *len = scenario == 5 ? sizeof(int) - 1 : sizeof(int);
        return 0;
    }
}
""" + feature + cache + """
int main(void)
{
    for (scenario = 0; scenario <= 9; ++scenario) {
        bool absent = scenario == 2 || scenario >= 7;
        legacy_calls = 0;
        assert(sysctl_for_bool("hw.optional.arm.FEAT_CSSC") == (scenario == 0));
        assert(legacy_calls == 0);
        assert(sysctl_for_feature("hw.optional.arm.FEAT_LSE",
                                  "hw.optional.armv8_1_atomics") ==
               (scenario == 0 || scenario == 2));
        assert(legacy_calls == absent);
    }
    for (scenario = 0; scenario <= 8; ++scenario) {
        int isize = 0, dsize = 0;
        int expected = scenario == 0 ? 128 : scenario == 1 ? 64 : 0;
        sys_cache_info(&isize, &dsize);
        assert(isize == expected && dsize == expected);
    }
    puts("Darwin AArch64 ISA and cache sysctl probes: passed");
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
