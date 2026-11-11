#!/usr/bin/env python3
"""QTest regression checks for the NCR53C710 register contract.

The HP 715 exposes the NCR53C710 through the LASI wrapper.  Byte accesses in
that wrapper reverse the low two address bits, so each NCR register byte is
addressed as (register ^ 3).
"""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import tempfile
from pathlib import Path


LASI_HPA_715 = 0xF0100000
LASI_SCSI = 0x6000
LASI_NCR710_BASE = 0x100
NCR_BASE = LASI_HPA_715 + LASI_SCSI + LASI_NCR710_BASE

SCNTL0 = 0x00
SCNTL1 = 0x01
SDID = 0x02
SODL = 0x06
SSTAT0 = 0x0D
SSTAT1 = 0x0E
CTEST1 = 0x15
CTEST2 = 0x16
ISTAT = 0x21
CTEST8 = 0x22
LCRC = 0x23
DMODE = 0x38

SCNTL1_RST = 0x08
SSTAT0_RST = 0x02
SSTAT1_OLF = 0x20
SSTAT1_RSTI = 0x02
CTEST2_SIGP = 0x40
ISTAT_SIGP = 0x20
ISTAT_RST = 0x40
ISTAT_ABRT = 0x80
DSTAT_ABRT = 0x10


def reg_addr(reg: int) -> int:
    return NCR_BASE + (reg ^ 3)


class QTest:
    def __init__(self, qemu: str) -> None:
        self.tmp = tempfile.TemporaryDirectory(prefix="ncr710-qtest-")
        self.sock_path = str(Path(self.tmp.name) / "qtest.sock")
        self.listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.listener.bind(self.sock_path)
        self.listener.listen(1)
        self.listener.settimeout(20)

        cmd = [
            qemu,
            "-qtest", f"unix:{self.sock_path}",
            "-qtest-log", "/dev/null",
            "-display", "none",
            "-audio", "none",
            "-machine", "715",
            "-drive", "if=scsi,file=null-co://,format=raw",
            "-accel", "qtest",
        ]
        self.proc = subprocess.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        try:
            self.conn, _ = self.listener.accept()
        except Exception:
            self.proc.terminate()
            stderr = self.proc.communicate(timeout=5)[1]
            raise RuntimeError(f"QEMU did not connect to qtest socket:\n{stderr}")
        self.file = self.conn.makefile("rwb", buffering=0)

    def close(self) -> None:
        try:
            self.file.close()
            self.conn.close()
            self.listener.close()
        finally:
            if self.proc.poll() is None:
                self.proc.terminate()
            try:
                _, stderr = self.proc.communicate(timeout=10)
            except subprocess.TimeoutExpired:
                self.proc.kill()
                _, stderr = self.proc.communicate()
            self.tmp.cleanup()
            if self.proc.returncode not in (0, -15):
                raise RuntimeError(
                    f"QEMU exited with {self.proc.returncode}:\n{stderr}"
                )

    def request(self, command: str) -> list[str]:
        self.file.write((command + "\n").encode("ascii"))
        while True:
            line = self.file.readline()
            if not line:
                stderr = self.proc.stderr.read() if self.proc.stderr else ""
                raise RuntimeError(
                    f"qtest connection closed while running {command!r}:\n{stderr}"
                )
            text = line.decode("ascii").strip()
            if text.startswith("OK"):
                return text.split()
            if text.startswith("FAIL"):
                raise AssertionError(f"qtest rejected {command!r}: {text}")
            # Ignore asynchronous qtest notifications; these tests do not
            # intercept IRQs, but the protocol permits async lines.

    def readb(self, reg: int) -> int:
        words = self.request(f"readb 0x{reg_addr(reg):x}")
        return int(words[1], 0)

    def writeb(self, reg: int, value: int) -> None:
        self.request(f"writeb 0x{reg_addr(reg):x} 0x{value:02x}")


def assert_equal(actual: int, expected: int, what: str) -> None:
    if actual != expected:
        raise AssertionError(
            f"{what}: expected 0x{expected:02x}, got 0x{actual:02x}"
        )


def main() -> int:
    if len(sys.argv) != 2:
        print(f"usage: {sys.argv[0]} QEMU-SYSTEM-HPPA", file=sys.stderr)
        return 2

    qemu = os.path.abspath(sys.argv[1])
    qt = QTest(qemu)
    try:
        # Sanity-check that the expected 53C710 register window is mapped.
        assert_equal(qt.readb(SCNTL0), 0xC0, "SCNTL0 reset value")

        # SDID is an eight-bit one-hot SCSI ID register (ID7..ID0).
        qt.writeb(SDID, 0x80)
        assert_equal(qt.readb(SDID), 0x80, "SDID must retain target ID 7")

        # LCRC is R/W, but every write clears it to zero regardless of data.
        qt.writeb(LCRC, 0xA5)
        assert_equal(qt.readb(LCRC), 0x00, "LCRC write-clear semantics")

        # CTEST1 and CTEST2 are read-only.
        ctest1 = qt.readb(CTEST1)
        qt.writeb(CTEST1, ctest1 ^ 0xFF)
        assert_equal(qt.readb(CTEST1), ctest1, "CTEST1 must ignore writes")

        ctest2 = qt.readb(CTEST2)
        qt.writeb(CTEST2, ctest2 ^ 0xFF)
        assert_equal(qt.readb(CTEST2), ctest2, "CTEST2 must ignore writes")

        # CTEST8 must read its own state, not ISTAT.  FM is bit 1.
        qt.writeb(CTEST8, 0x02)
        if (qt.readb(CTEST8) & 0x03) != 0x02:
            raise AssertionError("CTEST8 FM bit did not read back from CTEST8")

        # CTEST2.SIGP mirrors ISTAT.SIGP, and reading CTEST2 clears ISTAT.SIGP.
        qt.writeb(ISTAT, ISTAT_SIGP)
        if not (qt.readb(CTEST2) & CTEST2_SIGP):
            raise AssertionError("CTEST2.SIGP did not mirror ISTAT.SIGP")
        if qt.readb(ISTAT) & ISTAT_SIGP:
            raise AssertionError("reading CTEST2 did not clear ISTAT.SIGP")

        # Writing SODL makes the SCSI output data latch full (SSTAT1.OLF).
        qt.writeb(SODL, 0x5A)
        if not (qt.readb(SSTAT1) & SSTAT1_OLF):
            raise AssertionError("SSTAT1.OLF did not reflect a full SODL")

        # SCNTL1.RST asserts the external SCSI reset signal; it must not reset
        # the 53C710 itself, and the line remains asserted until software clears
        # SCNTL1.RST.
        qt.writeb(DMODE, 0x5A)
        qt.writeb(SCNTL1, SCNTL1_RST)
        assert_equal(qt.readb(DMODE), 0x5A, "SCNTL1.RST must not reset DMODE")
        if not (qt.readb(SCNTL1) & SCNTL1_RST):
            raise AssertionError("SCNTL1.RST did not remain asserted")
        if not (qt.readb(SSTAT1) & SSTAT1_RSTI):
            raise AssertionError("SSTAT1.RSTI did not reflect asserted SCSI RST")
        qt.writeb(SCNTL1, 0x00)
        if qt.readb(SSTAT1) & SSTAT1_RSTI:
            raise AssertionError("SSTAT1.RSTI remained set after SCSI RST cleared")
        # Reading SSTAT0 clears the latched bus-reset interrupt status.
        _ = qt.readb(SSTAT0)

        # ISTAT.RST is the chip software reset.  It resets registers to their
        # defaults without asserting SCSI RST and remains set until cleared.
        qt.writeb(DMODE, 0x5A)
        qt.writeb(ISTAT, ISTAT_RST)
        assert_equal(qt.readb(DMODE), 0x00, "ISTAT.RST must reset DMODE")
        if not (qt.readb(ISTAT) & ISTAT_RST):
            raise AssertionError("ISTAT.RST self-cleared")
        if qt.readb(SSTAT1) & SSTAT1_RSTI:
            raise AssertionError("ISTAT.RST incorrectly asserted SCSI RST")
        qt.writeb(ISTAT, 0x00)

        # ABRT status survives clearing ISTAT.ABRT until DSTAT is read.
        qt.writeb(ISTAT, ISTAT_ABRT)
        qt.writeb(ISTAT, 0x00)
        # DSTAT is at 0x0c; use an inline constant because reading it clears it.
        dstat = qt.readb(0x0C)
        if not (dstat & DSTAT_ABRT):
            raise AssertionError("DSTAT.ABRT was lost before DSTAT was read")

        print("NCR53C710 register contract: PASS")
        return 0
    finally:
        qt.close()


if __name__ == "__main__":
    raise SystemExit(main())
