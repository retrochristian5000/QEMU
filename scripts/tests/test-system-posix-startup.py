#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0-or-later
"""Guard shared QEMU system executable startup across POSIX hosts.

This source-policy test complements, but does not replace, native macOS
execution tests. No guest or cross toolchain is needed.
"""

from __future__ import annotations

import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]


class SystemPosixStartupTests(unittest.TestCase):
    def test_all_system_emulators_share_executable_path_init(self):
        main = (ROOT / "system/vl.c").read_text(encoding="utf-8")
        util = (ROOT / "util/cutils.c").read_text(encoding="utf-8")
        self.assertIn("qemu_init_exec_dir(argv[0]);", main)
        self.assertIn("void qemu_init_exec_dir(const char *argv0)", util)
        self.assertIn("exec_dir = CONFIG_BINDIR;", util)

    def test_darwin_resizes_executable_path_and_keeps_fallbacks(self):
        source = (ROOT / "util/cutils.c").read_text(encoding="utf-8")
        darwin = source.split("#elif defined(__APPLE__)", 1)[1].split(
            "#elif defined(__HAIKU__)", 1
        )[0]
        self.assertIn("_NSGetExecutablePath(fpath, &len)", darwin)
        self.assertIn("len > sizeof(fpath)", darwin)
        self.assertIn("g_malloc(len)", darwin)
        self.assertIn("_NSGetExecutablePath(long_path, &len)", darwin)
        self.assertIn("realpath(fpath, NULL)", darwin)
        self.assertIn("realpath(long_path, NULL)", darwin)
        self.assertNotIn("return;", darwin)
        self.assertIn("if (!p && argv0)", source)
        self.assertIn("free(resolved_path);", source)

    def test_posix_startup_uses_initialized_sigaction(self):
        source = (ROOT / "os-posix.c").read_text(encoding="utf-8")
        self.assertIn("struct sigaction act = { 0 };", source)
        self.assertIn("sigaction(SIGPIPE, &act, NULL);", source)
        self.assertIn("sigaction(SIGTSTP, &ignore, NULL);", source)
        self.assertIn("sigaction(SIGTTOU, &ignore, NULL);", source)
        self.assertIn("sigaction(SIGTTIN, &ignore, NULL);", source)
        for signal in ("SIGTSTP", "SIGTTOU", "SIGTTIN"):
            self.assertNotIn(f"signal({signal}, SIG_IGN)", source)


if __name__ == "__main__":
    unittest.main()
