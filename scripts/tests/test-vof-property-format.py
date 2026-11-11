#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Compile and exercise QEMU's VOF property trace formatter in isolation.

The exact production C function is extracted; only GLib's g_strlcpy helper is
substituted in this focused host-side test. This does not emulate VOF firmware.
"""

from pathlib import Path
import os
import shlex
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "hw/ppc/vof.c"


def main() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    begin = source.index("static void prop_format(")
    end = source.index("\nstatic int get_path(", begin)
    function = source[begin:end]
    assert "g_strlcpy" in function
    assert "strncpy(" not in function and "strcpy(" not in function
    assert "strcat(" not in function

    harness = r"""
#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* Test-only equivalent of GLib's NUL-terminating g_strlcpy contract. */
static size_t g_strlcpy(char *dst, const char *src, size_t size)
{
    size_t length = strlen(src);
    if (size) {
        size_t count = length < size - 1 ? length : size - 1;
        memcpy(dst, src, count);
        dst[count] = '\0';
    }
    return length;
}
""" + function + r"""

static void check(const unsigned char *src, int length, const char *expected)
{
    char data[32];
    int capacity;

    memset(data, 0x7f, sizeof(data));
    prop_format(data, sizeof(data), src, length);
    if (strcmp(data, expected) != 0) {
        fprintf(stderr, "expected <%s>, got <%s>\n", expected, data);
        exit(1);
    }

    for (capacity = 0; capacity <= 12; capacity++) {
        char guarded[16];
        memset(guarded, 0x7f, sizeof(guarded));
        prop_format(guarded + 1, capacity, src, length);
        if (guarded[0] != 0x7f || guarded[capacity + 1] != 0x7f) {
            fprintf(stderr, "buffer canary overwritten at %d\n", capacity);
            exit(2);
        }
        if (capacity && !memchr(guarded + 1, '\0', capacity)) {
            fprintf(stderr, "missing NUL terminator at %d\n", capacity);
            exit(3);
        }
    }
}

int main(void)
{
    const unsigned char words[] = "hello";
    const unsigned char binary[] = { 0, 1, 2, 3, 4, 5 };

    check(words, sizeof(words), "hello");
    check(binary, sizeof(binary), "00010203 0405");
    check(NULL, 0, "");
    puts("VOF property formatter: bounds and terminators verified");
    return 0;
}
"""
    cc = shlex.split(os.environ.get("CC_FOR_BUILD", "cc"))
    if len(cc) != 1:
        raise RuntimeError("CC_FOR_BUILD must identify one native compiler")
    with tempfile.TemporaryDirectory(prefix="qemu-vof-c-") as temp:
        program = Path(temp) / "vof-format-test"
        text = Path(temp) / "vof-format-test.c"
        text.write_text(harness, encoding="utf-8")
        subprocess.run(
            [cc[0], "-std=c11", "-Wall", "-Wextra", "-Werror",
             str(text), "-o", str(program)],
            check=True,
        )
        subprocess.run([str(program)], check=True)


if __name__ == "__main__":
    main()
