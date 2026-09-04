#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later

from pathlib import Path
import subprocess

EXPECTED_RAW = {
    "hw/net/eepro100.c": 1,
    "hw/net/rocker/rocker.c": 11,
    "hw/net/rocker/rocker_of_dpa.c": 19,
    "hw/ppc/spapr.c": 1,
    "hw/ppc/vof.c": 1,
    "hw/scsi/scsi-generic.c": 1,
    "hw/vfio/pci.c": 1,
    "include/disas/dis-asm.h": 1,
    "libdecnumber/dpd/decimal128.c": 2,
    "libdecnumber/dpd/decimal32.c": 2,
    "libdecnumber/dpd/decimal64.c": 2,
    "qga/vss-win32/install.cpp": 5,
    "system/runstate.c": 1,
    "target/m68k/translate.c": 3,
    "target/rx/disas.c": 1,
    "target/xtensa/xtensa-isa.c": 19,
}

EXPECTED_CHANGED = set(EXPECTED_RAW) | {"disas/m68k.c"}


def text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def write(path: str, data: str) -> None:
    Path(path).write_text(data, encoding="utf-8")


def replace(path: str, old: str, new: str, count: int) -> None:
    data = text(path)
    actual = data.count(old)
    if actual != count:
        raise SystemExit(
            f"{path}: expected {count} occurrence(s) of {old!r}, found {actual}"
        )
    write(path, data.replace(old, new))


def raw_count(path: str) -> int:
    # This deliberately counts only the exact libc call token, not wrappers.
    return text(path).count("sprintf(") + text(path).count("sprintf (")


def main() -> None:
    total = 0
    for path, expected in EXPECTED_RAW.items():
        actual = raw_count(path)
        if actual != expected:
            raise SystemExit(
                f"{path}: expected {expected} raw sprintf call(s), found {actual}"
            )
        total += actual
    if total != 71:
        raise SystemExit(f"expected 71 audited raw sprintf calls, found {total}")

    replace(
        "hw/net/eepro100.c",
        'p += sprintf(p, " %02x", *buf++);',
        'p += snprintf(p, sizeof(dump) - (p - dump), " %02x", *buf++);',
        1,
    )

    replace(
        "hw/net/rocker/rocker.c",
        "sprintf(ring_name,",
        "snprintf(ring_name, sizeof(ring_name),",
        3,
    )
    replace(
        "hw/net/rocker/rocker.c",
        "sprintf(buf,",
        "snprintf(buf, sizeof(buf),",
        8,
    )

    replace(
        "hw/net/rocker/rocker_of_dpa.c",
        "b += sprintf(b,",
        "b += snprintf(b, sizeof(buf) - (b - buf),",
        19,
    )

    replace(
        "hw/ppc/spapr.c",
        "sprintf(mem_name,",
        "snprintf(mem_name, sizeof(mem_name),",
        1,
    )
    replace(
        "hw/ppc/vof.c",
        "t += sprintf(t,",
        "t += snprintf(t, tlen - (t - tval),",
        1,
    )

    replace(
        "hw/scsi/scsi-generic.c",
        "    char *line_buffer, *p;\n\n    line_buffer = g_malloc(len * 5 + 1);",
        "    char *line_buffer, *p;\n    size_t line_buffer_size = len * 5 + 1;\n\n    line_buffer = g_malloc(line_buffer_size);",
        1,
    )
    replace(
        "hw/scsi/scsi-generic.c",
        'p += sprintf(p, " 0x%02x", cmd[i]);',
        'p += snprintf(p, line_buffer_size - (p - line_buffer),\n'
        '                      " 0x%02x", cmd[i]);',
        1,
    )

    replace(
        "hw/vfio/pci.c",
        "sprintf(tmp,",
        "snprintf(tmp, sizeof(tmp),",
        1,
    )

    replace(
        "include/disas/dis-asm.h",
        '#define sprintf_vma(s,x) sprintf (s, "%0" PRIx64, x)\n',
        "",
        1,
    )
    replace(
        "disas/m68k.c",
        "sprintf_vma (buf, disp);",
        "snprintf_vma(buf, sizeof(buf), disp);",
        1,
    )
    replace(
        "disas/m68k.c",
        "sprintf_vma (vmabuf, outer_disp);",
        "snprintf_vma(vmabuf, sizeof(vmabuf), outer_disp);",
        1,
    )

    for path in (
        "libdecnumber/dpd/decimal128.c",
        "libdecnumber/dpd/decimal32.c",
        "libdecnumber/dpd/decimal64.c",
    ):
        replace(path, "sprintf(&buf[j],", "snprintf(&buf[j], 3,", 2)

    replace(
        "qga/vss-win32/install.cpp",
        "sprintf(key,",
        "snprintf(key, sizeof(key),",
        5,
    )

    replace(
        "system/runstate.c",
        "            buf = g_malloc(len * 3);",
        "            buf = g_malloc(len * 3 + 1);",
        1,
    )
    replace(
        "system/runstate.c",
        '                    sprintf(buf + 3 * i, "%02x ", message[i]);',
        '                    snprintf(buf + 3 * i, len * 3 + 1 - 3 * i,\n'
        '                             "%02x ",\n'
        '                             (unsigned int)(unsigned char)message[i]);',
        1,
    )

    replace(
        "target/m68k/translate.c",
        'sprintf(p, "D%d", i);',
        'snprintf(p, 3, "D%d", i);',
        1,
    )
    replace(
        "target/m68k/translate.c",
        'sprintf(p, "A%d", i);',
        'snprintf(p, 3, "A%d", i);',
        1,
    )
    replace(
        "target/m68k/translate.c",
        'sprintf(p, "ACC%d", i);',
        'snprintf(p, 5, "ACC%d", i);',
        1,
    )

    replace(
        "target/rx/disas.c",
        "sprintf(out,",
        "snprintf(out, 8,",
        1,
    )

    replace(
        "target/xtensa/xtensa-isa.c",
        "sprintf(xtisa_error_msg,",
        "snprintf(xtisa_error_msg, sizeof(xtisa_error_msg),",
        19,
    )

    subprocess.run(
        ["python3", "scripts/tests/check-unbounded-format.py"], check=True
    )

    changed = set(
        subprocess.check_output(
            ["git", "diff", "--name-only"], text=True
        ).splitlines()
    )
    if changed != EXPECTED_CHANGED:
        missing = sorted(EXPECTED_CHANGED - changed)
        extra = sorted(changed - EXPECTED_CHANGED)
        raise SystemExit(f"changed-file mismatch: missing={missing}, extra={extra}")


if __name__ == "__main__":
    main()
