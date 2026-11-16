#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Static contract regression for Linux-only header detection in Meson.

This checks source-selection and configuration guards, not a native macOS
compile or link. Run it alongside Meson/CI integration tests.
"""

from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[2]
MESON = (ROOT / "meson.build").read_text(encoding="utf-8")


class LinuxHeaderGateTests(unittest.TestCase):
    def test_kernel_uapi_config_probes_require_linux(self):
        names = (
            "CONFIG_LINUX_MAGIC_H",
            "HAVE_BTRFS_H",
            "HAVE_OPENAT2_H",
            "CONFIG_BLKZONED",
            "CONFIG_FALLOCATE_PUNCH_HOLE",
            "CONFIG_FALLOCATE_ZERO_RANGE",
            "CONFIG_FIEMAP",
            "CONFIG_PRCTL_PR_SET_TIMERSLACK",
            "CONFIG_RTNETLINK",
            "HAVE_FSXATTR",
        )
        for name in names:
            with self.subTest(config=name):
                pattern = (
                    r"config_host_data\.set\('"
                    + re.escape(name)
                    + r"',\s*host_os == 'linux' and\b"
                )
                self.assertRegex(MESON, pattern)

    def test_l2tpv3_requires_linux_even_if_headers_are_visible(self):
        self.assertRegex(
            MESON,
            r"get_option\('l2tpv3'\)\.require\(host_os == 'linux'",
        )
        self.assertIn("#include <linux/ip.h>",
                      (ROOT / "net/l2tpv3.c").read_text(encoding="utf-8"))
        self.assertIn("if have_l2tpv3",
                      (ROOT / "net/meson.build").read_text(encoding="utf-8"))

    def test_linux_backend_file_selection_remains_conditional(self):
        cases = (
            ("system/meson.build", "async-teardown.c"),
            ("hw/usb/meson.build", "u2f-passthru.c"),
            ("util/meson.build", "userfaultfd.c"),
        )
        for filename, source in cases:
            with self.subTest(source=source):
                value = (ROOT / filename).read_text(encoding="utf-8")
                guarded = re.search(
                    r"if host_os == 'linux'\s+"
                    r"(?:(?!endif).)*" + re.escape(source),
                    value,
                    re.DOTALL,
                )
                self.assertIsNotNone(guarded)

    def test_not_all_linux_named_features_are_linux_only(self):
        # FreeBSD's libinotify-kqueue can implement the inotify interface.
        self.assertIn("have_inotify_init1 = cc.has_header_symbol("
                      "'sys/inotify.h', 'inotify_init1')", MESON)
        # VirtIO protocol headers are emulated-device definitions, not host
        # kernel APIs. They must remain usable by macOS QEMU builds.
        self.assertIn("standard-headers/linux/virtio_blk.h",
                      (ROOT / "include/qemu/vhost-user-server.h")
                      .read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
