#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Check that FreeBSD-only build interfaces do not leak into Darwin.

Source-level regression only: cross-OS Meson configure/compile still needs
separate FreeBSD and macOS test hosts.
"""

from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[2]


def source(path):
    return (ROOT / path).read_text(encoding="utf-8")


class FreeBSDHostBoundaryTests(unittest.TestCase):
    def test_bsd_user_requires_implemented_freebsd_glue(self):
        meson = source("meson.build")
        self.assertIn(
            "have_bsd_user = have_bsd_user or (target.endswith('bsd-user') and",
            meson,
        )
        self.assertIn("host_os == 'freebsd')", meson)
        self.assertIn(
            "elif target.endswith('bsd-user')\n    if host_os != 'freebsd'",
            meson,
        )
        self.assertIn("subdir(host_os)", source("bsd-user/meson.build"))
        self.assertTrue((ROOT / "bsd-user/freebsd/meson.build").is_file())
        for os_name in ("darwin", "netbsd", "openbsd", "dragonfly"):
            with self.subTest(host=os_name):
                self.assertFalse((ROOT / "bsd-user" / os_name / "meson.build").exists())

    def test_unused_disk_header_is_not_in_common_block_core(self):
        self.assertNotIn("#include <sys/disk.h>", source("block.c"))
        self.assertNotIn("HAVE_SYS_DISK_H", source("block.c"))
        self.assertNotIn("HAVE_SYS_DISK_H", source("meson.build"))

    def test_darwin_pty_precedes_generic_header_discovery(self):
        part = source("chardev/char-pty.c").split(
            "#if defined CONFIG_DARWIN", 1
        )[1].split("#elif defined CONFIG_SOLARIS", 1)[0]
        self.assertIn("# include <util.h>", part)
        self.assertIn("# include <termios.h>", part)
        self.assertLess(part.index("# include <util.h>"),
                        part.index("#elif defined HAVE_PTY_H"))
        self.assertIn("# include <pty.h>", part)
        self.assertIn("#  include <libutil.h>", part)

    def test_shared_bsd_and_mac_interfaces_are_preserved(self):
        meson = source("meson.build")
        self.assertIn("config_host_data.set('CONFIG_BSD', host_os in bsd_oses)",
                      meson)
        self.assertIn("config_host_data.set('CONFIG_DARWIN', host_os == 'darwin')",
                      meson)
        self.assertIn(
            "config_host_data.set('HAVE_SYS_IOCCOM_H', cc.has_header('sys/ioccom.h'))",
            meson,
        )
        exit_parent = source("system/exit-with-parent.c")
        self.assertIn("#elif defined(__FreeBSD__)\n\n#include <sys/procctl.h>",
                      exit_parent)
        self.assertIn("#elif defined(__APPLE__)", exit_parent)
        self.assertIn("#include <sys/event.h>", exit_parent)


if __name__ == "__main__":
    unittest.main()
